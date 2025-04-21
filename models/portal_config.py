import requests
import pandas as pd
from odoo import models, fields, api
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
            return False

        # Read Excel data
        df = pd.read_excel(response.content)
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

    def _prepare_description(self, row):
        # Combine all additional fields into notes
        excluded_fields = ['id', 'name', 'email', 'phone', 'city']
        notes = []
        for column in row.index:
            if column not in excluded_fields and row[column]:
                notes.append(f"{column}: {row[column]}")
        return '\n'.join(notes)
