import requests
import pandas as pd
import tempfile
import os
from odoo import models, fields, api
from odoo.exceptions import UserError
from urllib.parse import quote

class PortalConfig(models.Model):
    _name = 'portal.config'
    name = fields.Char('Name', required=True)
    login_url = fields.Char('Login URL', required=True, default='https://www.cindrebay.in/action.php')
    data_url = fields.Char('Data URL', required=True, default='https://www.cindrebay.in/download-data.php')e, default='https://www.cindrebay.in/action.php')
    username = fields.Char('Username', required=True) default='https://www.cindrebay.in/download-data.php')
    password = fields.Char('Password', required=True)rue)
    last_sync = fields.Datetime('Last Sync Date')quired=True)
    active = fields.Boolean(default=True)    last_sync = fields.Datetime('Last Sync Date')
(default=True)
    def _get_session(self):
        session = requests.Session()elf):
        login_data = {
            'inputUsrNme': self.username,
            'inputPassword': quote(self.password)   'inputUsrNme': self.username,
        }
        session.post(self.login_url, data=login_data)
        return session        session.post(self.login_url, data=login_data)

    def sync_leads(self):
        self.ensure_one()
        session = self._get_session()self.ensure_one()
        ession()
        # Download Excel file
        response = session.get(self.data_url)
        if response.status_code != 200:on.get(self.data_url)
            return False        if response.status_code != 200:

        # Read Excel data
        df = pd.read_excel(response.content)temporary file
        Lead = self.env['crm.lead']ffix='.xlsx', delete=False) as temp_file:
        SyncLog = self.env['lead.sync.log']            temp_file.write(response.content)
me
        for _, row in df.iterrows():
            if SyncLog.search([('external_id', '=', str(row['id']))]):
                continue            # Read Excel data with explicit engine
mp_path, engine='openpyxl')
            # Prepare lead values
            vals = {d']
                'name': row['name'],og']
                'email_from': row['email'],
                'phone': row['phone'],s():
                'city': row['city'],w['id']))]):
                'description': self._prepare_description(row),       continue
            }
 lead values
            # Create lead
            lead = Lead.create(vals)        'name': row['name'],
            _from': row['email'],
            # Log the sync row['phone'],
            SyncLog.create({
                'external_id': str(row['id']),self._prepare_description(row),
                'lead_id': lead.id,  }
            })

        self.last_sync = fields.Datetime.now()d = Lead.create(vals)
        return True                

    def _prepare_description(self, row):
        # Combine all additional fields into notes
        excluded_fields = ['id', 'name', 'email', 'phone', 'city']  'lead_id': lead.id,
        notes = []
        for column in row.index:
            if column not in excluded_fields and row[column]:
                notes.append(f"{column}: {row[column]}")
        return '\n'.join(notes)

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
