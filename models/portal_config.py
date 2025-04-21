import requests
import pandas as pd
import tempfile
import os
from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
from bs4 import BeautifulSoup

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

        # Check content type and size
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('application/'):
            raise UserError(f"Unexpected content type: {content_type}. Please check if session is valid.")

        # Save and process file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        try:
            df = None
            errors = []

            # Try different formats
            for engine, ext in [('openpyxl', '.xlsx'), ('xlrd', '.xls')]:
                try:
                    os.rename(temp_path, temp_path + ext)
                    df = pd.read_excel(temp_path + ext, engine=engine)
                    temp_path = temp_path + ext
                    break
                except Exception as e:
                    errors.append(f"{engine} attempt failed: {str(e)}")
                    os.rename(temp_path + ext, temp_path)

            # Try CSV as last resort
            if df is None:
                try:
                    df = pd.read_csv(temp_path)
                except Exception as e:
                    errors.append(f"CSV attempt failed: {str(e)}")

            if df is None:
                raise UserError(f"Failed to read file in any format. Errors:\n" + "\n".join(errors))

            if df.empty:
                raise UserError("No data found in the downloaded file")

            # Rest of the processing
            Lead = self.env['crm.lead']
            SyncLog = self.env['lead.sync.log']

            for _, row in df.iterrows():
                if SyncLog.search([('external_id', '=', str(row['id']))]):
                    continue

                # Prepare lead values
                vals = {
                    'name': row['name'],
                    'email_from': row['email'],
                    'phone': row['phone'],
                    'city': row['city'],
                    'description': self._prepare_description(row),
                }

                # Create lead
                lead = Lead.create(vals)
                
                # Log the sync
                SyncLog.create({
                    'external_id': str(row['id']),
                    'lead_id': lead.id,
                })

            self.last_sync = fields.Datetime.now()
            return True

        except Exception as e:
            _logger.error(f"Error details: {str(e)}", exc_info=True)
            raise UserError(f"Error processing file: {str(e)}")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _prepare_description(self, row):
        # Combine all additional fields into notes
        excluded_fields = ['id', 'name', 'email', 'phone', 'city']
        notes = []
        for column in row.index:
            if column not in excluded_fields and row[column]:
                notes.append(f"{column}: {row[column]}")
        return '\n'.join(notes)
