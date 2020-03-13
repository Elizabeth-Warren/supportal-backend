"""
TODO: You'll need to write an email service here like

abstract class EmailService: 
	def send_email(
            template_name,
            from_email,
            recipient,
            reply_to_email,
            configuration_set_name,
            payload,
            application_name
        ):
        # sends an email
        return s

    def send_bulk_email(
        configuration_set_name,
        default_template_data,
        from_email,
        payload_array,
        reply_to_email,
        template,
        application_name):
        # sends email to a list of people
        return
	
"""
# from ew_common.email_service import EmailService

_email_service = None


def get_email_service():
    global _email_service
    # if _email_service is None:
    #     _email_service = EmailService()
    return _email_service
