from odoo import models


class Attendee(models.Model):
    _inherit = 'calendar.attendee'

    def _compute_mail_tz(self):

        filtered = self.filtered(lambda r: r.event_id.appointment_type_id and r.event_id.appointment_type_id.appointment_tz)

        for attendee in filtered:
            attendee.mail_tz = attendee.event_id.appointment_type_id.appointment_tz

        super(Attendee, self - filtered)._compute_mail_tz()

    def _should_notify_attendee(self):
        """ Notify all attendees for meeting linked to appointment type """
        return self.event_id.appointment_type_id or super()._should_notify_attendee()
