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
        session.post(self.login_url, data=login_data)
        return session

    def sync_leads(self):
        self.ensure_one()
        session = self._get_session()
        
        # Download Excel file
        response = session.get(self.data_url)
        if response.status_code != 200:
            raise UserError("Failed to download file from portal")

        # Save response content to temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        try:
            # Detect file type
            file_type = magic.from_file(temp_path, mime=True)
            
            if file_type == 'application/vnd.ms-excel':
                # Old .xls format
                df = pd.read_excel(temp_path, engine='xlrd')
            elif file_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                             'application/zip']:
                # New .xlsx format
                df = pd.read_excel(temp_path, engine='openpyxl')
            else:
                raise UserError(f"Unsupported file format: {file_type}")
            
            if df.empty:
                raise UserError("No data found in the downloaded file")

            required_columns = ['id', 'name', 'email', 'phone', 'city']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise UserError(f"Missing required columns: {', '.join(missing_columns)}")

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

        except pd.errors.EmptyDataError:
            raise UserError("The Excel file is empty")
        except Exception as e:
            raise UserError(f"Error processing Excel file: {str(e)}")
        finally:
            # Clean up temporary file
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
