{
    'name': 'Portal Lead Sync',
    'version': '17.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Sync leads from external PHP portal',
    'depends': ['crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/portal_config_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
