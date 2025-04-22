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

    name = fields.Char('Name', required=True)
    login_url = fields.Char('Login URL', required=True, default='https://www.cindrebay.in/action.php')
    data_url = fields.Char('Data URL', required=True, default='https://www.cindrebay.in/download-data.php')
    username = fields.Char('Username', required=True)
    password = fields.Char('Password', required=True)
    last_sync = fields.Datetime('Last Sync Date')
    active = fields.Boolean(default=True)
    days_to_sync = fields.Integer('Days to Sync', default=7, 
        help="Number of days to look back for leads")

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

    def _get_random_team(self):
        teams = self.env['crm.team'].search([('active', '=', True)])
        return choice(teams).id if teams else False

    def _get_lms_source(self):
        Source = self.env['utm.source']
        lms_source = Source.search([('name', '=', 'LMS')], limit=1)
        if not lms_source:
            lms_source = Source.create({'name': 'LMS'})
        return lms_source.id

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
            Lead = self.env['crm.lead']
            SyncLog = self.env['lead.sync.log']

            for _, row in df.iterrows():
                row_dict = row.fillna('').astype(str).to_dict()
                
                if SyncLog.search([('external_id', '=', row_dict['id'])]):
                    continue

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
                    'team_id': self._get_random_team(),
                    'course_id': self._get_course_product(row_dict.get('course')),
                    'source_id': self._get_lms_source(),
                }

                lead = Lead.create(vals)
                
                # Log the sync
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
