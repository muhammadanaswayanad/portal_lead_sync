import requests
import pandas as pd
import tempfile
import os
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

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

    def _get_session(self):
        session = requests.Session()
        
        # Add browser-like headers
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        # First visit login page
        session.get('https://www.cindrebay.in/login.php')
        
        login_data = {
            'inputUsrNme': self.username,
            'inputPassword': self.password,
            'submit': 'Login'
        }
        
        # Post login and follow redirects
        response = session.post(self.login_url, data=login_data, allow_redirects=True)
        _logger.info(f"Login final URL: {response.url}")
        
        # Verify login success by checking if redirected to home.php
        if 'home.php' not in response.url:
            raise UserError("Login failed - Please check credentials")
            
        return session

    def sync_leads(self):
        self.ensure_one()
        session = self._get_session()

        # Download the file as .xls
        response = session.get(self.data_url)
        if response.status_code != 200:
            raise UserError("Failed to download file from portal")

        # Save as .xls since that's what the server sends
        with tempfile.NamedTemporaryFile(suffix='.xls', delete=False) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        try:
            # Try reading with xlrd for .xls files
            df = pd.read_excel(temp_path, engine='xlrd')
            
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
            raise UserError(f"Error processing Excel file: {str(e)}")
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
