{
    'name': 'Portal Lead Sync',
    'version': '1.0',
    'summary': 'Synchronize leads from external portal',
    'description': """
        This module allows synchronization of leads from external portal
        and assigns them to sales teams based on location matching.
    """,
    'category': 'CRM',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'crm'],
    'data': [
        'views/crm_team_views.xml',
        'security/ir.model.access.csv',
        'views/portal_config_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
