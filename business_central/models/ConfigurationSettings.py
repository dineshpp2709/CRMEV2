# -*- coding: utf-8 -*-

from odoo import _, api, fields, models

class ResConfigSettings(models.TransientModel):
	_inherit = 'res.config.settings'

	bc_username = fields.Char("Username", config_parameter='bc.username')
	bc_password = fields.Char("Password", config_parameter='bc.password')
	bc_base_url = fields.Char("Base Url", config_parameter='bc.base_url')
	