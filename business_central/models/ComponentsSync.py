from requests import auth
from odoo import api, fields, models
from itertools import groupby

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class ComponentSyncLogs(models.Model):
    _name = 'business_central.component_logs'
    _description = "Component Sync Logs"
    _order = 'id desc'
    
    name = fields.Char("Message")
    message = fields.Text("Description")
    ref = fields.Text("References")
    active = fields.Boolean("Active", default=True)
    request = fields.Text("Request")
    debug_mode = fields.Boolean("Debug Mode")

    def _log_error(self, short_message, message, ref, request='', mode=False):
        self.sudo().create({
            'name': short_message,
            'message': message,
            'ref': ref,
            'request': request,
            'debug_mode': mode
        })

    def _cps_get_process_logs(self):
        return self.env.ref("business_central.action_component_sync_logs").read()[0]

class ComponentSync(models.Model):
    _inherit = 'stock.production.lot'

    bc_cps_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], "Component Sync Status",default='pending')
    
    def _cps_run_process(self, debug_mode = False):
        try:
            synced_serial_numbers = self.sudo().search([('bc_cps_state','=','done')])
            product_model = self.env['product.product'].sudo()
            subassembly_model = self.env['school_net.subassembly'].sudo()

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            #url_filter = ' or '.join(list(map(lambda x: "('itemNo' not eq '%s')"%(x.name) , synced_serial_numbers)))
            
            url = "%s/CompSerialNo?$filter('RecordSynced' eq false)"%(base_url)	
            #if url_filter and False:
            #    url = '%s?$filter=%s'%(url,url_filter)		
            
            response = requests.get(url, auth=token, headers=headers)
            if response and response.ok:
                data = response.json()
                key = (lambda x: (x.get('serialNo',''), x.get('itemNo','')))
                for key,group in groupby(sorted(data.get('value',[]), key=key), key=key):
                    serial_number = self.sudo().search([('bc_cps_state','!=','done'),('name','=',key[0]),('product_id.snet_item_code','=',key[1])], limit=1)
                    synced = True
                    system_ids = []
                    try:
                        vals = list(group)
                        if serial_number:
                            for comp in vals:
                                product = product_model.search([('snet_item_code','=',comp.get('componentItemNo',''))], limit=1)
                                if product:
                                    component = self.sudo().search([('name','=',comp.get('componentSerialNo','')), ('product_id','=',product.id)], limit=1)
                                    if not component:
                                        component = self.sudo().create({'name': comp.get('componentSerialNo',''), 'product_id':product.id, 'company_id':self.env.company.id, 'snet_available_stock':False, 'snet_location': serial_number.snet_location and serial_number.snet_location.id or False})
                                    
                                    if component:
                                        assembly = subassembly_model.create({'name': component.id, 'snet_parent_id': serial_number.id})
                                        if not assembly:
                                            raise Exception("Failed to link component '%s' with parent serial no. '%s'"%(component.name, serial_number.name))
                                        system_ids.append(comp.get('systemId',''))
                                    else:
                                        raise Exception("Failed to create component '%s' for item '%s'"%(comp.get('componentSerialNo',''), comp.get('componentItemNo','')))
                                else:
                                    raise Exception("Product '%s' not found in the system."%(comp.get('componentItemNo','')))
                        else:
                            raise Exception("Parent Serial Number '%s' for item '%s' not found in system."%(key[0],key[1]))
                    except Exception as e:
                        synced = False
                        self.env['business_central.component_logs']._log_error('Error while Syncing Records', str(e), 'error', debug_mode and traceback.format_exc() or '', debug_mode)
                    if synced:
                        serial_number.bc_cps_state = 'done'

                        #update serial no.
                        for system_id in system_ids:
                            component_url = '%s/CompSerialNo(%s)'%(base_url,system_id)
                            headers['If-Match'] = '*'
                            component_response = requests.patch(component_url, data=json.dumps({'RecordSynced':'true'}), auth=token, headers=headers)
                            if component_response and component_response.ok:
                                pass
                                #All is well
                            else:
                                self.env['business_central.component_logs']._log_error('Error while Updating Component', str(response.text), system_id, debug_mode and traceback.format_exc() or '', debug_mode)
                    else:
                        serial_number.snet_components = False
            else:
                raise Exception(response.text)

        except Exception as e:        
            self.env['business_central.component_logs']._log_error('Error while Syncing Records', str(e), 'error', debug_mode and traceback.format_exc() or '', debug_mode)
                        
                
            
    def _cron_component_sync(self):
        self._cps_run_process()

    def _cps_pending_records(self):
        return self.search_count([('bc_cps_state','in',['pending'])])

    def _cps_failed_records(self):
        return self.search_count([('bc_cps_state','in',['fail'])])
    
    def _cps_done_records(self):
        return self.search_count([('bc_cps_state','in',['done'])])
    
    def _cps_total_records(self):
        return self.search_count([])
    
    def _cps_get_final_records(self):
        return self.env.ref('business_central.action_component_sync_final').read()[0]

    def _cps_get_pending_records(self):
        return self.env.ref('business_central.action_component_sync_pending').read()[0]
    
    def _cps_get_all_records(self):
        return self.env.ref('business_central.action_component_sync').read()[0]

    def _cps_get_processed_records(self):
        return self.env.ref('business_central.action_component_sync_done').read()[0]

    def _cps_get_failed_records(self):
        return self.env.ref('business_central.action_component_sync_failed').read()[0]
