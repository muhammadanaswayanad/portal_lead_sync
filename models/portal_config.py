import requests
import pandas as pd
import tempfile
import os
import magic
from odoo import models, fields, api
from odoo.exceptions import UserError
from urllib.parse import quote

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
        login_data = {
            'inputUsrNme': self.username,
            'inputPassword': quote(self.password)
        }
        response = session.post(self.login_url, data=login_data)
        
        # Check if login was successful by looking for HTML login form
        if 'login' in response.text.lower() or 'password' in response.text.lower():
            raise UserError("Login failed - please check credentials")
            
        return session

    def sync_leads(self):
        self.ensure_one()
        session = self._get_session()
        
        # Download Excel file
        response = session.get(self.data_url)
        if response.status_code != 200:
            raise UserError("Failed to download file from portal")

        # Check if response is HTML instead of Excel
        content_type = response.headers.get('content-type', '').lower()
        if 'html' in content_type or response.content.startswith(b'<!DOCTYPE'):
            raise UserError("Received HTML instead of Excel file - session may have expired")

        # Save and process Excel file
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        try:
            df = pd.read_excel(temp_path, engine='openpyxl')
            
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
