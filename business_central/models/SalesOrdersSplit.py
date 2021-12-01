# -*- coding: utf-8 -*-
from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

from itertools import groupby

GSTTypes = {
    "regular": 'Registered',
    "unregistered": 'Unregistered',
    "overseas": 'Export',
    "deemed_export": 'Deemed Export',
    "consumer": 'Exempted',
    "special_economic_zone": 'SEZ Development',
}

line_transform = (lambda line, x: {
            "DocType": "Invoice",
            "DocNo": x.order_id.name and x.order_id.name[0:20] or '',
            "LineNo": line,
            "LineType": 'item',
            "ItemNo": x.product_id and x.product_id.snet_item_code and x.product_id.snet_item_code[0:10] or '',
            "Description" : x.product_id and x.product_id.name and x.product_id.name[0:100] or '',
            "Quantity" : x.product_uom_qty,
            "UOM": x.product_uom and x.product_uom.snet_uom_code[0:10] or '',
            "UnitPrice" : x.price_unit,
            "bc_product_id": x.product_id and x.product_id.id or False,
            "bc_sale_line_id": x.id,
            'name': '%s - %s'%(x.order_id.name and x.order_id.name[0:20] or '', line)
        })

data_transform = (lambda x: {
        "DocumentType" : 'Invoice',
        "OrderNo" : x.name and x.name[0:20] or '',
        "CustomerNo" : x.partner_id and x.partner_id.snet_customer_code[0:20] or '',
        "OrderDate" : x.date_order and x.date_order.strftime("%Y-%m-%d"),
        "LocationCode" : x.warehouse_id and x.warehouse_id.code[0:10],
        "Salesperson" : x.user_id and x.user_id.snet_salesperson_code[0:20] or '',
        "PaymentTerms" : x.payment_term_id and x.payment_term_id.snet_payment_term_code[0:10] or '',
        "CustReference" : x.client_order_ref and x.client_order_ref[0:30] or '',
        "GSTType" : GSTTypes.get(x.l10n_in_gst_treatment,'') or '',
        "CurrencyCode" : x.currency_id and x.currency_id.name[0:10] or '',
        "NoOfLines" : x.order_line and len(x.order_line) or 0,
        "LineAmountTotal" : x.amount_untaxed,
        "FinRegion" : x.snet_fin_region and x.snet_fin_region.code[0:20] or '',
        "FinCostCentre" : x.snet_fin_cost_center and x.snet_fin_cost_center.code[0:20] or '',
        "FinPractice" : x.snet_fin_practice and x.snet_fin_practice.code[0:20] or '',
        "FinBusiness" : x.snet_fin_business and x.snet_fin_business.code[0:20] or '',
        "FinBranch" : x.snet_fin_branch and x.snet_fin_branch.code[0:20] or '',
        "FinZone" : x.snet_fin_zone and x.snet_fin_zone.code[0:20] or '',
        "saleslines": [(0,0,line_transform(lineno, line)) for lineno, line in enumerate(x.order_line.filtered(lambda x: x.product_id),10000)],
        'sale_order': x.id,
        'delivery_address': x[0].partner_shipping_id.id
    })

address_line_data = (lambda line, x, ordername: {
    "DocType": "Invoice",
    "DocNo": ordername,
    "LineNo": line,
    "LineType": 'item',
    "ItemNo": x.snet_sale_order_line.product_id and x.snet_sale_order_line.product_id.snet_item_code and x.snet_sale_order_line.product_id.snet_item_code[0:10] or '',
    "Description" : x.snet_sale_order_line.product_id and x.snet_sale_order_line.product_id.name and x.snet_sale_order_line.product_id.name[0:100] or '',
    "Quantity" : x.snet_quantity,
    "UOM": x.snet_sale_order_line.product_uom and x.snet_sale_order_line.product_uom.snet_uom_code[0:10] or '',
    "UnitPrice" : x.snet_sale_order_line.price_unit,
    "bc_product_id": x.snet_sale_order_line.product_id and x.snet_sale_order_line.product_id.id or False,
    "bc_sale_line_id": x.snet_sale_order_line.id,
    'name': '%s - %s'%(ordername, line)
})

address_data_transform = (lambda order, x: x and {
    "DocumentType" : 'Invoice',
    "OrderNo" : '%s-%d'%(x[0].snet_sale_order.name and x[0].snet_sale_order.name[0:20] or '', order),
    "CustomerNo" : x[0].snet_sale_order.partner_id and x[0].snet_sale_order.partner_id.snet_customer_code[0:20] or '',
    "OrderDate" : x[0].snet_sale_order.date_order and x[0].snet_sale_order.date_order.strftime("%Y-%m-%d"),
    "LocationCode" : x[0].snet_sale_order.warehouse_id and x[0].snet_sale_order.warehouse_id.code[0:10],
    "Salesperson" : x[0].snet_sale_order.user_id and x[0].snet_sale_order.user_id.snet_salesperson_code[0:20] or '',
    "PaymentTerms" : x[0].snet_sale_order.payment_term_id and x[0].snet_sale_order.payment_term_id.snet_payment_term_code[0:10] or '',
    "CustReference" : x[0].snet_sale_order.client_order_ref and x[0].snet_sale_order.client_order_ref[0:30] or '',
    "GSTType" : GSTTypes.get(x[0].snet_sale_order.l10n_in_gst_treatment,'') or '',
    "CurrencyCode" : x[0].snet_sale_order.currency_id and x[0].snet_sale_order.currency_id.name[0:10] or '',
    "NoOfLines" : len(x),
    "LineAmountTotal" : x[0].snet_sale_order.amount_untaxed,
    "FinRegion" : x[0].snet_sale_order.snet_fin_region and x[0].snet_sale_order.snet_fin_region.code[0:20] or '',
    "FinCostCentre" : x[0].snet_sale_order.snet_fin_cost_center and x[0].snet_sale_order.snet_fin_cost_center.code[0:20] or '',
    "FinPractice" : x[0].snet_sale_order.snet_fin_practice and x[0].snet_sale_order.snet_fin_practice.code[0:20] or '',
    "FinBusiness" : x[0].snet_sale_order.snet_fin_business and x[0].snet_sale_order.snet_fin_business.code[0:20] or '',
    "FinBranch" : x[0].snet_sale_order.snet_fin_branch and x[0].snet_sale_order.snet_fin_branch.code[0:20] or '',
    "FinZone" : x[0].snet_sale_order.snet_fin_zone and x[0].snet_sale_order.snet_fin_zone.code[0:20] or '',
    "saleslines": [(0,0,address_line_data(lineno, line, '%s-%d'%(x[0].snet_sale_order.name and x[0].snet_sale_order.name[0:20] or '', order))) for lineno, line in enumerate(x,10000)],
    'sale_order': x[0].snet_sale_order.id,
    'delivery_address': x[0].snet_delivery_address.id
})
class SalesOrderLines(models.Model):
    _inherit = 'sale.order.line'

    snet_quantity_reserved = fields.Boolean("Quantity Reserved")
    
class SalesOrderSplit(models.Model):
    _inherit = 'sale.order'

    bs_stock_available = fields.Boolean("Stock Available", compute="_compute_stock_available", store=True)
    bs_stock_reserved = fields.Boolean("Stock Reserved", compute="_compute_stock_reserved", store=True)
    bs_resync_available = fields.Boolean("Re-Sync Available", compute="_compute_resync_available")

    def _compute_resync_available(self):
        for record in self:
            records = self.env['business_central.sale_order_staging'].sudo().search([('sale_order','=',record.id)])
            record.bs_resync_available = any(filter(lambda x: x in ['pending','fail'], records.mapped('bc_sos_state')))
    
    @api.depends("order_line.snet_quantity_reserved")
    def _compute_stock_reserved(self):
        for record in self:
            record.bs_stock_reserved = all(record.mapped("order_line.snet_quantity_reserved"))
    
    @api.depends("order_line.product_uom_qty")
    def _compute_stock_available(self):
        available_stock = self.env['school_net.available_stock'].sudo()
        for record in self:
            quantity_required = list(map(lambda x:(x.product_id.id, x.product_uom_qty),record.order_line)) 
            products_for_location = {x.snet_product_id.id : x.snet_qty_in_hand for x in available_stock.search([('snet_location_id','=',record.warehouse_id.id),('snet_product_id','in',record.order_line.mapped('product_id.id'))])}
            record.bs_stock_available = all([products_for_location.get(x[0],0) >= x[1] for x in quantity_required])
            
    def _action_confirm(self):
        res = super(SalesOrderSplit, self)._action_confirm()
        self.action_setup_request()
        return res
    
    def action_unlink_request(self):
        records = self.env['business_central.sale_order_staging'].sudo().search([('sale_order','in',self.ids),('bc_sos_state','!=','done')])
        if records:
            records.unlink()

    def action_setup_request(self):
        self.action_unlink_request()
        records = []
        staging = self.env['business_central.sale_order_staging'].sudo()
        for record in self:
            if record.snet_delivery_address:
                sort_key = (lambda x: x.snet_delivery_address.id) 
                #TDE: Short Hand this
                index = 1
                for key, group in groupby(sorted(record.snet_delivery_address, key = sort_key), key = sort_key):
                    data = list(group)
                    existing_order = staging.search([('sale_order','=',record.id),('bc_sos_state','=','done'),('delivery_address','=',key)])
                    if not existing_order:
                        records.append(address_data_transform(index, data))
                    index += 1 
            else:
                existing_order = staging.search([('sale_order','=',record.id),('bc_sos_state','=','done'),('delivery_address','=',record.partner_shipping_id.id)])
                if not existing_order: 
                    transformed_data = data_transform(record)
                    records.append(transformed_data)                
        
        self.env['business_central.sale_order_staging'].sudo().create(records)

    def unlink(self):
        self.action_unlink_request()
        return super(SalesOrderSplit, self).unlink()
    
    def action_cancel(self):
        res = super(SalesOrderSplit, self).action_cancel()
        self.action_unlink_request()
        return res
    
    def action_reserve_stocks(self):
        for record in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')
            
            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            
            
            url = "%s/itemreservation"%(base_url)
            for line in record.order_line:
                if line.product_id and not line.snet_quantity_reserved:
                    data = {
                            "itemNo": line.product_id.snet_item_code[0:10],
                            "locationCode": record.warehouse_id.code[0:10],
                            "quantity":line.product_uom_qty,
                            "CustomerNo": record.partner_id.snet_customer_code[0:20],
                            "QuoteNo":record.name
                        }
                    response = requests.post(url, data=json.dumps(data), auth=token, headers=headers)
                    if response and response.ok:
                        data = response.json()
                        line.snet_quantity_reserved = True
                    else:
                        res = json.loads(response.text)
                        record.message_post(body="Error while reserving stock for product '%s'. Error: %s"%(line.name, res['error']['message']))
        return {'tag': 'reload'}            
                
