# -*- coding: utf-8 -*-

from odoo import api, fields, models

class Integrations(models.Model):
    _inherit = 'school_net.integrations'

    type = fields.Selection(selection_add=[('BC','Business Central')])