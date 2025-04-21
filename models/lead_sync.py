from odoo import models, fields

class LeadSyncLog(models.Model):
    _name = 'lead.sync.log'
    _description = 'Lead Sync Log'

    external_id = fields.Char('External ID', required=True, index=True)
    lead_id = fields.Many2one('crm.lead', string='Lead', required=True)
    create_date = fields.Datetime('Created On', readonly=True)
