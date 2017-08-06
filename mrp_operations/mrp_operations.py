# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo import models
import operator
import time
from datetime import datetime
from odoo.tools.translate import _
from odoo.exceptions import UserError

#----------------------------------------------------------
# Work Centers
#----------------------------------------------------------
# capacity_hour : capacity per hour. default: 1.0.
#          Eg: If 5 concurrent operations at one time: capacity = 5 (because 5 employees)
# unit_per_cycle : how many units are produced for one cycle

class stock_move(models.Model):
    _inherit = 'stock.move'

        'move_dest_id_lines': fields.One2many('stock.move','move_dest_id', 'Children Moves')


class mrp_production_workcenter_line(models.Model):

    def _get_date_end(self, field_name, arg):
        """ Finds ending date.
        @return: Dictionary of values.
        """
        ops = self.browse(ids)
        date_and_hours_by_cal = [(op.date_planned, op.hour, op.workcenter_id.calendar_id.id) for op in ops if op.date_planned]

        intervals = self.env['resource.calendar'].interval_get_multi(date_and_hours_by_cal)

        res = {}
        for op in ops:
            res[op.id] = False
            if op.date_planned:
                i = intervals.get((op.date_planned, op.hour, op.workcenter_id.calendar_id.id))
                if i:
                    res[op.id] = i[-1][1].strftime('%Y-%m-%d %H:%M:%S')
                else:
                    res[op.id] = op.date_planned
        return res

    def onchange_production_id(self, production_id):
        if not production_id:
            return {}
        production = self.env['mrp.production'].browse(production_id)
        result = {
            'product': production.product_id.id,
            'qty': production.product_qty,
            'uom': production.product_uom.id,
        }
        return {'value': result}

    def _search_date_planned_end(self, obj, name, args):
        op_mapping = {
            '<': operator.lt,
            '>': operator.gt,
            '<=': operator.le,
            '>=': operator.ge,
            '=': operator.eq,
            '!=': operator.ne,
        }
        res = []
        for field, op, value in args:
            assert field in ['date_planned_end'], 'Invalid domain left operand'
            assert op in op_mapping.keys(), 'Invalid domain operator'
            assert isinstance(value, basestring) or isinstance(value, bool), 'Invalid domain right operand'

            ids = []
            workcenter_line_ids = self.search([])
            for line in self.browse(workcenter_line_ids):
                if isinstance(value, bool) and op_mapping[op](bool(line[field]), value):
                    ids.append(line.id)
                elif isinstance(value, basestring) and op_mapping[op](str(line[field])[:len(value)], value):
                    ids.append(line.id)
            res.append(('id', 'in', ids))

        return res

    _inherit = 'mrp.production.workcenter.line'
    _order = "sequence, date_planned"


   state = fields.Selection([('draft','Draft'),('cancel','Cancelled'),('pause','Pending'),('startworking', 'In Progress'),('done','Finished')],'Status', readonly=True, copy=False
                                 help="* When a work order is created it is set in 'Draft' status.\n" \
                                       "* When user sets work order in start mode that time it will be set in 'In Progress' status.\n" \
                                       "* When work order is in running mode, during that time if user wants to stop or to make changes in order then can set in 'Pending' status.\n" \
                                       "* When the user cancels the work order it will be set in 'Canceled' status.\n" \
                                       "* When order is completely processed that time it is set in 'Finished' status."),
   date_planned = fields.Datetime('Scheduled Date', index=True)
   date_planned_end = fields.Datetime(compute="_get_date_end", string='End Date', fnct_search=_search_date_planned_end)
   date_start = fields.Datetime('Start Date')
   date_finished = fields.Datetime('End Date')
   delay = fields.Float('Working Hours',help="The elapsed time between operation start and stop in this Work Center",readonly=True)
   production_state = fields.Related('production_id','state'
            type='selection',
            selection=[('draft','Draft'),('confirmed','Waiting Goods'),('ready','Ready to Produce'),('in_production','In Production'),('cancel','Canceled'),('done','Done')],
            string='Production Status', readonly=True),
   product = fields.Related('production_id','product_id',type='many2one',relation='product.product',string='Product'
            readonly=True),
   qty = fields.Related('production_id','product_qty',type='float',string='Qty',readonly=True, store=True)
   uom = fields.Related('production_id','product_uom',type='many2one',relation='product.uom',string='Unit of Measure',readonly=True)


    _defaults = {
        'state': 'draft',
        'delay': 0.0,
        'production_state': 'draft'
    }

    def modify_production_order_state(self, action):
        """ Modifies production order state if work order state is changed.
        @param action: Action to perform.
        @return: Nothing
        """
        prod_obj_pool = self.env['mrp.production']
        oper_obj = self.browse(ids)[0]
        prod_obj = oper_obj.production_id
        if action == 'start':
            if prod_obj.state =='confirmed':
                prod_obj_pool.force_production([prod_obj.id])
                prod_obj_pool.signal_workflow([prod_obj.id], 'button_produce')
            elif prod_obj.state =='ready':
                prod_obj_pool.signal_workflow([prod_obj.id], 'button_produce')
            elif prod_obj.state =='in_production':
                return
            else:
                raise UserError(_('Manufacturing order cannot be started in state "%s"!') % (prod_obj.state,))
        else:
            open_count = self.search_count(cr,uid,[('production_id','=',prod_obj.id), ('state', '!=', 'done')])
            flag = not bool(open_count)
            if flag:
                button_produce_done = True
                for production in prod_obj_pool.browse([prod_obj.id]):
                    if production.move_lines or production.move_created_ids:
                        moves = production.move_lines + production.move_created_ids
                        # If tracking is activated, we want to make sure the user will enter the
                        # serial numbers.
                        if moves.filtered(lambda r: r.product_id.tracking != 'none'):
                            button_produce_done = False
                        else:
                            prod_obj_pool.action_produce(cr,uid, production.id, production.product_qty, 'consume_produce', context = None)
                if button_produce_done:
                    prod_obj_pool.signal_workflow([oper_obj.production_id.id], 'button_produce_done')
        return

    def write(self, vals, update=True):
        result = super(mrp_production_workcenter_line, self).write(ids, vals)
        prod_obj = self.env['mrp.production']
        if vals.get('date_planned', False) and update:
            for prod in self.browse(ids):
                if prod.production_id.workcenter_lines:
                    dstart = min(vals['date_planned'], prod.production_id.workcenter_lines[0]['date_planned'])
                    prod_obj.write([prod.production_id.id], {'date_start':dstart}, mini=False)
        return result

    def action_draft(self):
        """ Sets state to draft.
        @return: True
        """
        return self.write(ids, {'state': 'draft'})

    def action_start_working(self):
        """ Sets state to start working and writes starting date.
        @return: True
        """
        self.modify_production_order_state(ids, 'start')
        self.write(ids, {'state':'startworking', 'date_start': time.strftime('%Y-%m-%d %H:%M:%S')})
        return True

    def action_done(self):
        """ Sets state to done, writes finish date and calculates delay.
        @return: True
        """
        delay = 0.0
        date_now = time.strftime('%Y-%m-%d %H:%M:%S')
        obj_line = self.browse(ids[0])

        date_start = datetime.strptime(obj_line.date_start,'%Y-%m-%d %H:%M:%S')
        date_finished = datetime.strptime(date_now,'%Y-%m-%d %H:%M:%S')
        delay += (date_finished-date_start).days * 24
        delay += (date_finished-date_start).seconds / float(60*60)

        self.write(ids, {'state':'done', 'date_finished': date_now,'delay':delay})
        self.modify_production_order_state(cr,uid,ids,'done')
        return True

    def action_cancel(self):
        """ Sets state to cancel.
        @return: True
        """
        return self.write(ids, {'state':'cancel'})

    def action_pause(self):
        """ Sets state to pause.
        @return: True
        """
        return self.write(ids, {'state':'pause'})

    def action_resume(self):
        """ Sets state to startworking.
        @return: True
        """
        return self.write(ids, {'state':'startworking'})


class mrp_production(models.Model):
    _inherit = 'mrp.production'

    allow_reorder = fields.Boolean('Free Serialisation', help="Check this to be able to move independently all production orders, without moving dependent ones.")


    def _production_date_end(self, prop, unknow_none):
        """ Calculates planned end date of production order.
        @return: Dictionary of values
        """
        result = {}
        for prod in self.browse(ids):
            result[prod.id] = prod.date_planned
            for line in prod.workcenter_lines:
                result[prod.id] = max(line.date_planned_end, result[prod.id])
        return result

    def action_production_end(self):
        """ Finishes work order if production order is done.
        @return: Super method
        """
        obj = self.browse(ids)[0]
        workcenter_pool = self.env['mrp.production.workcenter.line']
        for workcenter_line in obj.workcenter_lines:
            if workcenter_line.state == 'draft':
                workcenter_line.signal_workflow('button_start_working')
            workcenter_line.signal_workflow('button_done')
        return super(mrp_production,self).action_production_end(ids)

    def action_in_production(self):
        """ Changes state to In Production and writes starting date.
        @return: True
        """
        workcenter_pool = self.env['mrp.production.workcenter.line']
        for prod in self.browse(ids):
            if prod.workcenter_lines:
                workcenter_pool.signal_workflow([prod.workcenter_lines[0].id], 'button_start_working')
        return super(mrp_production,self).action_in_production(ids)
    
    def action_cancel(self):
        """ Cancels work order if production order is canceled.
        @return: Super method
        """
        workcenter_pool = self.env['mrp.production.workcenter.line']
        obj = self.browse(ids,context=context)[0]
        workcenter_pool.signal_workflow([record.id for record in obj.workcenter_lines], 'button_cancel')
        return super(mrp_production,self).action_cancel(cr,uid,ids,context=context)

    def _compute_planned_workcenter(self, mini=False):
        """ Computes planned and finished dates for work order.
        @return: Calculated date
        """
        dt_end = datetime.now()
        if context is None:
            context = {}
        for po in self.browse(ids):
            dt_end = datetime.strptime(po.date_planned, '%Y-%m-%d %H:%M:%S')
            if not po.date_start:
                self.write([po.id], {
                    'date_start': po.date_planned
                }, update=False)
            old = None
            for wci in range(len(po.workcenter_lines)):
                wc  = po.workcenter_lines[wci]
                if (old is None) or (wc.sequence>old):
                    dt = dt_end
                if context.get('__last_update'):
                    del context['__last_update']
                if (wc.date_planned < dt.strftime('%Y-%m-%d %H:%M:%S')) or mini:
                    self.env['mrp.production.workcenter.line'].write([wc.id],  {
                        'date_planned': dt.strftime('%Y-%m-%d %H:%M:%S')
                    }, update=False)
                    i = self.env['resource.calendar'].interval_get(
                        cr,
                        uid,
                        #passing False makes resource_resource._schedule_hours run 1000 iterations doing nothing
                        wc.workcenter_id.calendar_id and wc.workcenter_id.calendar_id.id or None,
                        dt,
                        wc.hour or 0.0
                    )
                    if i:
                        dt_end = max(dt_end, i[-1][1])
                else:
                    dt_end = datetime.strptime(wc.date_planned_end, '%Y-%m-%d %H:%M:%S')

                old = wc.sequence or 0
            super(mrp_production, self).write([po.id], {
                'date_finished': dt_end
            })
        return dt_end

    def _move_pass(self):
        """ Calculates start date for stock moves finding interval from resource calendar.
        @return: True
        """
        for po in self.browse(ids):
            if po.allow_reorder:
                continue
            todo = list(po.move_lines)
            dt = datetime.strptime(po.date_start,'%Y-%m-%d %H:%M:%S')
            while todo:
                l = todo.pop(0)
                if l.state in ('done','cancel','draft'):
                    continue
                todo += l.move_dest_id_lines
                date_end = l.production_id.date_finished
                if date_end and datetime.strptime(date_end, '%Y-%m-%d %H:%M:%S') > dt:
                    if l.production_id.state not in ('done','cancel'):
                        for wc in l.production_id.workcenter_lines:
                            i = self.env['resource.calendar'].interval_min_get(
                                cr,
                                uid,
                                wc.workcenter_id.calendar_id.id or False,
                                dt, wc.hour or 0.0
                            )
                            dt = i[0][0]
                        if l.production_id.date_start > dt.strftime('%Y-%m-%d %H:%M:%S'):
                            self.write([l.production_id.id], {'date_start':dt.strftime('%Y-%m-%d %H:%M:%S')}, mini=True)
        return True

    def _move_futur(self):
        """ Calculates start date for stock moves.
        @return: True
        """
        for po in self.browse(ids):
            if po.allow_reorder:
                continue
            for line in po.move_created_ids:
                l = line
                while l.move_dest_id:
                    l = l.move_dest_id
                    if l.state in ('done','cancel','draft'):
                        break
                    if l.production_id.state in ('done','cancel'):
                        break
                    if l.production_id and (l.production_id.date_start < po.date_finished):
                        self.write([l.production_id.id], {'date_start': po.date_finished})
                        break
        return True


    def write(self, vals, update=True, mini=True):
        direction = {}
        if vals.get('date_start', False):
            for po in self.browse(ids):
                direction[po.id] = cmp(po.date_start, vals.get('date_start', False))
        result = super(mrp_production, self).write(ids, vals)
        if (vals.get('workcenter_lines', False) or vals.get('date_start', False) or vals.get('date_planned', False)) and update:
            self._compute_planned_workcenter(ids, mini=mini)
        for d in direction:
            if direction[d] == 1:
                # the production order has been moved to the passed
                self._move_pass([d])
                pass
            elif direction[d] == -1:
                self._move_futur([d])
                # the production order has been moved to the future
                pass
        return result

    def action_compute(self, properties=None):
        """ Computes bills of material of a product and planned date of work order.
        @param properties: List containing dictionaries of properties.
        @return: No. of products.
        """
        result = super(mrp_production, self).action_compute(ids, properties=properties)
        self._compute_planned_workcenter(ids)
        return result


class mrp_operations_operation_code(models.Model):
    _name="mrp_operations.operation.code"
    _columns={
    name = fields.Char('Operation Name', required=True)
    code = fields.Char('Code', size=16, required=True)
    start_stop = fields.Selection([('start','Start'),('pause','Pause'),('resume','Resume'),('cancel','Cancelled'),('done','Done')], 'Status', required=True)
    }

class mrp_operations_operation(models.Model):
    _name="mrp_operations.operation"

    def _order_date_search_production(self):
        """ Finds operations for a production order.
        @return: List of ids
        """
        operation_ids = self.env['mrp_operations.operation'].search([('production_id','=',ids[0])])
        return operation_ids

    def _get_order_date(self, field_name, arg):
        """ Calculates planned date for an operation.
        @return: Dictionary of values
        """
        res={}
        operation_obj = self.browse(ids)
        for operation in operation_obj:
                res[operation.id] = operation.production_id.date_planned
        return res

    def calc_delay(self, vals):
        """ Calculates delay of work order.
        @return: Delay
        """
        code_lst = []
        time_lst = []

        code_ids = self.env['mrp_operations.operation.code'].search([('id','=',vals['code_id'])])
        code = self.env['mrp_operations.operation.code'].browse(code_ids)[0]

        oper_ids = self.search(cr,uid,[('production_id','=',vals['production_id']),('workcenter_id','=',vals['workcenter_id'])])
        oper_objs = self.browse(cr,uid,oper_ids)

        for oper in oper_objs:
            code_lst.append(oper.code_id.start_stop)
            time_lst.append(oper.date_start)

        code_lst.append(code.start_stop)
        time_lst.append(vals['date_start'])
        diff = 0
        for i in range(0,len(code_lst)):
            if code_lst[i] == 'pause' or code_lst[i] == 'done' or code_lst[i] == 'cancel':
                if not i: continue
                if code_lst[i-1] not in ('resume','start'):
                   continue
                a = datetime.strptime(time_lst[i-1],'%Y-%m-%d %H:%M:%S')
                b = datetime.strptime(time_lst[i],'%Y-%m-%d %H:%M:%S')
                diff += (b-a).days * 24
                diff += (b-a).seconds / float(60*60)
        return diff

    def check_operation(self, vals):
        """ Finds which operation is called ie. start, pause, done, cancel.
        @param vals: Dictionary of values.
        @return: True or False
        """
        code_ids=self.env['mrp_operations.operation.code'].search(cr,uid,[('id','=',vals['code_id'])])
        code=self.env['mrp_operations.operation.code'].browse(cr,uid,code_ids)[0]
        code_lst = []
        oper_ids=self.search(cr,uid,[('production_id','=',vals['production_id']),('workcenter_id','=',vals['workcenter_id'])])
        oper_objs=self.browse(cr,uid,oper_ids)

        if not oper_objs:
            if code.start_stop!='start':
                raise UserError(_('Operation is not started yet!'))
                return False
        else:
            for oper in oper_objs:
                 code_lst.append(oper.code_id.start_stop)
            if code.start_stop=='start':
                    if 'start' in code_lst:
                        raise UserError(_('Operation has already started! You can either Pause/Finish/Cancel the operation.'))
                        return False
            if code.start_stop=='pause':
                    if  code_lst[len(code_lst)-1]!='resume' and code_lst[len(code_lst)-1]!='start':
                        raise UserError(_('In order to Pause the operation, it must be in the Start or Resume state!'))
                        return False
            if code.start_stop=='resume':
                if code_lst[len(code_lst)-1]!='pause':
                   raise UserError(_('In order to Resume the operation, it must be in the Pause state!'))
                   return False

            if code.start_stop=='done':
               if code_lst[len(code_lst)-1]!='start' and code_lst[len(code_lst)-1]!='resume':
                  raise UserError(_('In order to Finish the operation, it must be in the Start or Resume state!'))
                  return False
               if 'cancel' in code_lst:
                  raise UserError(_('Operation is Already Cancelled!'))
                  return False
            if code.start_stop=='cancel':
               if  not 'start' in code_lst :
                   raise UserError(_('No operation to cancel.'))
                   return False
               if 'done' in code_lst:
                  raise UserError(_('Operation is already finished!'))
                  return False
        return True

    def write(self, vals):
        oper_objs = self.browse(ids)[0]
        vals['production_id']=oper_objs.production_id.id
        vals['workcenter_id']=oper_objs.workcenter_id.id

        if 'code_id' in vals:
            self.check_operation(vals)

        if 'date_start' in vals:
            vals['date_start']=vals['date_start']
            vals['code_id']=oper_objs.code_id.id
            delay=self.calc_delay(vals)
            wc_op_id=self.env['mrp.production.workcenter.line'].search(cr,uid,[('workcenter_id','=',vals['workcenter_id']),('production_id','=',vals['production_id'])])
            self.env['mrp.production.workcenter.line'].write(cr,uid,wc_op_id,{'delay':delay})

        return super(mrp_operations_operation, self).write(ids, vals)

    def create(self, vals):
        workcenter_pool = self.env['mrp.production.workcenter.line']
        code_ids=self.env['mrp_operations.operation.code'].search(cr,uid,[('id','=',vals['code_id'])])
        code=self.env['mrp_operations.operation.code'].browse(code_ids)[0]
        wc_op_id=workcenter_pool.search(cr,uid,[('workcenter_id','=',vals['workcenter_id']),('production_id','=',vals['production_id'])])
        if code.start_stop in ('start','done','pause','cancel','resume'):
            if not wc_op_id:
                production_obj=self.env['mrp.production'].browse(vals['production_id'])
                wc_op_id.append(workcenter_pool.create(cr,uid,{'production_id':vals['production_id'],'name':production_obj.product_id.name,'workcenter_id':vals['workcenter_id']}))
            if code.start_stop=='start':
                workcenter_pool.action_start_working(cr,uid,wc_op_id)
                workcenter_pool.signal_workflow([wc_op_id[0]], 'button_start_working')

            if code.start_stop=='done':
                workcenter_pool.action_done(cr,uid,wc_op_id)
                workcenter_pool.signal_workflow([wc_op_id[0]], 'button_done')
                self.env['mrp.production'].write(cr,uid,vals['production_id'],{'date_finished':datetime.now().strftime('%Y-%m-%d %H:%M:%S')})

            if code.start_stop=='pause':
                workcenter_pool.action_pause(cr,uid,wc_op_id)
                workcenter_pool.signal_workflow([wc_op_id[0]], 'button_pause')

            if code.start_stop=='resume':
                workcenter_pool.action_resume(cr,uid,wc_op_id)
                workcenter_pool.signal_workflow([wc_op_id[0]], 'button_resume')

            if code.start_stop=='cancel':
                workcenter_pool.action_cancel(cr,uid,wc_op_id)
                workcenter_pool.signal_workflow([wc_op_id[0]], 'button_cancel')

        if not self.check_operation(vals):
            return
        delay=self.calc_delay(vals)
        line_vals = {}
        line_vals['delay'] = delay
        if vals.get('date_start',False):
            if code.start_stop == 'done':
                line_vals['date_finished'] = vals['date_start']
            elif code.start_stop == 'start':
                line_vals['date_start'] = vals['date_start']

        self.env['mrp.production.workcenter.line'].write(wc_op_id, line_vals)

        return super(mrp_operations_operation, self).create(vals)

    def initialize_workflow_instance(self):
        mrp_production_workcenter_line = self.env['mrp.production.workcenter.line']
        line_ids = mrp_production_workcenter_line.search([])
        mrp_production_workcenter_line.create_workflow(line_ids)
        return True

    _columns={
    production_id = fields.Many2one('mrp.production','Production',required=True)
    workcenter_id = fields.Many2one('mrp.workcenter','Work Center',required=True)
    code_id = fields.Many2one('mrp_operations.operation.code','Code',required=True)
    date_start = fields.Datetime('Start Date')
    date_finished = fields.Datetime('End Date')
    order_date = fields.Date(compute="_get_order_date",string='Order Date',store={'mrp.production':(_order_date_search_production,['date_planned'], 10)})
        }
    _defaults={
        'date_start': lambda *a:datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
