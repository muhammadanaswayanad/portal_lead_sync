from odoo import models, fields, api

class CrmTeam(models.Model):
    _inherit = 'crm.team'
    
    preferred_cities = fields.Char(
        string="Preferred Cities",
        help="Comma-separated list of cities this team prefers to handle. "
             "Used for automatic lead assignment based on city matching."
    )
