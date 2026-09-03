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


  ---

  urlReserve por el momento se agrego esta variables que tendria que acerce con el boton ver mi presupuesto ? . por el momento estoy redireccionando al home de SC

---
hasta donde tengo entendido.
para el caso de logos que esta flotando . no es posible dentro de otra seccion

---
seccion cruceros pendiente de agregar el lugar del crucero, se tiene que agregar antes de generar , por el momento lo llamare {{directionCruise}}