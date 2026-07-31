estoy viendo que se tienen
 {{#showSectionTrustPilot}}
  {{#truspilotInformation}}
  <script type="application/json+trustpilot">
        {
          "recipientEmail": "{{recipientEmail}}",
          "recipientName": "{{recipientName}}",
          "referenceId": "{{referenceId}}",
          "templateId": "{{templateId}}",
          "locale": "{{locale}}",
          "senderName": "{{senderName}}",
          "replyTo": "{{replyTo}}",
          "preferredSendTime": "{{preferredSendTime}}",
          "productReviewInvitationPreferredSendTime": "{{productReviewInvitationPreferredSendTime}}",
          "products": [
            {
              "productUrl": "{{productUrl}}",
              "imageUrl": "{{imageUrl}}",
              "name": "{{name}}",
              "sku": "{{sku}}",
            }
          ]
        }
    </script>
  {{/truspilotInformation}}
  {{/showSectionTrustPilot}}

  en el head, pero no vi en el cuerpo, necesitare un ejemplo visual de la seccion si existe, por el momento eh creado otro
  