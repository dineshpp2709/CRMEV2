# -*- coding: utf-8 -*-
# from odoo import http


# class BusinessCentral(http.Controller):
#     @http.route('/business_central/business_central/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/business_central/business_central/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('business_central.listing', {
#             'root': '/business_central/business_central',
#             'objects': http.request.env['business_central.business_central'].search([]),
#         })

#     @http.route('/business_central/business_central/objects/<model("business_central.business_central"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('business_central.object', {
#             'object': obj
#         })
