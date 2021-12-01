# -*- coding: utf-8 -*-
{
    #Status and System Id must be updated individually else system will not work.
    
    'name': "Business Central Integration",

    'summary': """
            Business Central Integration
        """,

    'description': """
        
    """,

    'author': "Squadsoftech",
    'website': "www.squadsoftech.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'School Net',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','school_net'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',

        'data/ScheduledTasks.xml',
        'data/Integrations.xml',
        
        'views/ConfigurationSettings.xml',
        'views/CustomerSync.xml',
        'views/ShippingAddressSync.xml',
        'views/SalesPersonSync.xml',
        'views/VendorSync.xml',
        'views/VendorAddressSync.xml',
        'views/LocationSync.xml',
        'views/ItemSync.xml',
        'views/SaleOrderSync.xml',
        'views/PurchaseOrderSync.xml',
        'views/BomSync.xml',
        'views/ExpenseSync.xml',
        'views/InvoiceSync.xml',
        'views/PostedExpenseSync.xml',
        'views/PaidExpenseSync.xml',
        'views/TermsConditionsSync.xml',
        'views/SerialNumbersSync.xml',
        'views/AvailableStockSync.xml',
        'views/ComponentSync.xml',
        'views/PartsSync.xml',
        'views/FixedAssetsSync.xml',
        'views/AssetsTransferSync.xml'
        
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
