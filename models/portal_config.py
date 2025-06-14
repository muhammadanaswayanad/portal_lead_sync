import requests
import pandas as pd
import tempfile
import os
from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
from bs4 import BeautifulSoup
from random import choice

_logger = logging.getLogger(__name__)

class PortalConfig(models.Model):
    _name = 'portal.config'
    _description = 'Portal Configuration'
    _rec_name = 'name'
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Configuration name must be unique!')
    ]

    name = fields.Char('Name', required=True)
    login_url = fields.Char('Login URL', required=True, default='https://www.cindrebay.in/action.php', 
                           help="URL for login authentication")
    data_url = fields.Char('Data URL', required=True, default='https://www.cindrebay.in/download-data.php', 
                          help="URL for downloading leads data")
    username = fields.Char('Username', required=True, help="Portal login username")
    password = fields.Char('Password', required=True, help="Portal login password")
    last_sync = fields.Datetime('Last Sync Date', readonly=True)
    active = fields.Boolean(default=True, index=True)
    days_to_sync = fields.Integer('Days to Sync', default=7, 
        help="Number of days to look back for leads")

    @api.model
    def get_default_config(self):
        """Get the default active configuration"""
        return self.search([('active', '=', True)], limit=1)

    def _get_date_range(self):
        to_date = datetime.now()
        from_date = to_date - timedelta(days=self.days_to_sync)
        return {
            'from': from_date.strftime('%Y-%m-%d'),
            'to': to_date.strftime('%Y-%m-%d')
        }

    def _get_session(self):
        session = requests.Session()
        
        # Add browser-like headers
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })
        
        # Get login page and extract any hidden fields
        login_page = session.get('https://www.cindrebay.in/login.php')
        soup = BeautifulSoup(login_page.text, 'html.parser')
        login_form = soup.find('form')
        
        # Build login data with any hidden fields
        login_data = {
            'inputUsrNme': self.username,
            'inputPassword': self.password,
            'submit': 'Login'
        }
        
        # Add any hidden fields from form
        if login_form:
            for hidden in login_form.find_all('input', type='hidden'):
                login_data[hidden['name']] = hidden['value']
        
        # Post login
        response = session.post(self.login_url, data=login_data)
        _logger.info(f"Login status: {response.status_code}")
        _logger.info(f"Login response content: {response.text[:500]}")  # Log first 500 chars
        
        # Check for login form or error messages in response
        soup = BeautifulSoup(response.text, 'html.parser')
        if soup.find('form', {'action': 'action.php'}) or 'invalid' in response.text.lower():
            raise UserError("Login failed - Please check credentials")
            
        return session

    def _get_course_product(self, course_name):
        if not course_name:
            return False
        return self.env['product.product'].search([
            ('name', 'ilike', course_name)
        ], limit=1).id

    def _get_team_by_city(self, city):
        """Find a team matching the preferred city list"""
        if not city:
            return False
            
        # Normalize the city name
        city = city.strip().lower()
        
        # Search for teams with matching preferred cities
        teams = self.env['crm.team'].sudo().search([('active', '=', True)])
        for team in teams:
            # Skip teams with no preferred_cities
            if not team.preferred_cities:
                continue
                
            # Split and normalize city names
            preferred_cities = [c.strip().lower() for c in team.preferred_cities.split(',')]
            
            # Check if city matches any preferred city
            if city in preferred_cities:
                return team.id
                
        # No match found, return False
        return False

    def _get_random_team(self, city=None):
        """Get a team by city preference or random if no match"""
        # Try to find team by city
        team_id = self._get_team_by_city(city)
        if team_id:
            return team_id
            
        # If no match, get any active team randomly
        teams = self.env['crm.team'].sudo().search([('active', '=', True)])
        return choice(teams).id if teams else False

    def _get_lms_source(self):
        Source = self.env['utm.source']
        lms_source = Source.search([('name', '=', 'LMS')], limit=1)
        if not lms_source:
            lms_source = Source.create({'name': 'LMS'})
        return lms_source.id

    def _find_duplicate_salesperson(self, email, phone):
        """Find salesperson of any existing leads with same email or phone"""
        if not email and not phone:
            return False
            
        domain = ['|']
        if email:
            domain.append(('email_from', '=ilike', email))
        else:
            domain.append(('email_from', '=', False))
            
        if phone:
            # Normalize phone number by removing spaces, dashes, etc.
            normalized_phone = ''.join(c for c in phone if c.isdigit())
            if normalized_phone:
                domain.append(('phone', 'ilike', normalized_phone))
        else:
            domain.append(('phone', '=', False))
            
        # Search for duplicate leads with assigned salesperson
        existing_lead = self.env['crm.lead'].sudo().search(domain + [('user_id', '!=', False)], limit=1)
        
        if existing_lead:
            return existing_lead.user_id.id
        return False

    def sync_leads(self):
        self.ensure_one()
        session = self._get_session()

        # Prepare filter parameters
        date_range = self._get_date_range()
        filter_data = {
            'from': date_range['from'],
            'to': date_range['to'],
            'city': '',
            'course': '',
            'status_search': '',
            'form_name': '',
            'OTP': '',
            'leadsource': ''
        }

        # First post to project-details.php to set filters
        session.post('https://www.cindrebay.in/project-details.php', data=filter_data)

        # Then get the filtered data
        response = session.get(self.data_url)
        _logger.info(f"Download response content: {response.content[:100]}")

        if b'No Record(s) Found!' in response.content:
            _logger.info("No new records found in date range")
            return True

        try:
            # Try reading as TSV
            df = pd.read_csv(pd.io.common.BytesIO(response.content), sep='\t')
            
            if df.empty:
                raise UserError("No data found in the downloaded file")

            # Normalize column names
            df.columns = df.columns.str.lower().str.strip()
            
            _logger.info(f"Columns found: {list(df.columns)}")
            
            # Validate required columns
            required_columns = ['id', 'name', 'email', 'phone', 'city']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                _logger.error(f"Available columns: {list(df.columns)}")
                raise UserError(f"Missing required columns: {', '.join(missing_columns)}")

            # Rest of the processing
            Lead = self.env['crm.lead'].sudo()  # Use sudo for lead creation
            SyncLog = self.env['lead.sync.log']

            for _, row in df.iterrows():
                row_dict = row.fillna('').astype(str).to_dict()
                
                if SyncLog.search([('external_id', '=', row_dict['id'])]):
                    continue

                # Check for duplicate salesperson
                existing_salesperson = self._find_duplicate_salesperson(
                    row_dict.get('email'), 
                    row_dict.get('phone')
                )

                # Prepare lead values with required fields
                vals = {
                    'name': row_dict['name'],
                    'email_from': row_dict['email'],
                    'phone': row_dict['phone'],
                    'city': row_dict['city'],
                    'description': self._prepare_description(row_dict),
                    'expected_revenue': 0.0,
                    'probability': 10.0,
                    'type': 'lead',
                    'team_id': self._get_random_team(row_dict.get('city')),
                    'course_id': self._get_course_product(row_dict.get('course')),
                    'source_id': self._get_lms_source(),
                    'user_id': existing_salesperson,  # Use existing salesperson if found, otherwise False
                    'partner_name': row_dict['name'],
                }

                # Create lead as superuser
                lead = Lead.create(vals)
                
                # Log the sync - no need for sudo here
                SyncLog.create({
                    'external_id': row_dict['id'],
                    'lead_id': lead.id,
                })

            self.last_sync = fields.Datetime.now()
            return True

        except Exception as e:
            _logger.error(f"Error details: {str(e)}", exc_info=True)
            raise UserError(f"Error processing file: {str(e)}")

    def _prepare_description(self, row_dict):
        # Combine all additional fields into notes
        excluded_fields = ['id', 'name', 'email', 'phone', 'city']
        notes = []
        for key, value in row_dict.items():
            if key not in excluded_fields and value:
                notes.append(f"{key}: {value}")
        return '\n'.join(notes)
