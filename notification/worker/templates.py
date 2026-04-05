ALERT_SUBJECT = "🚨 DENGUE ALERT: {risk_level} Risk in {planning_area}"

ALERT_BODY_TEXT = """Hello,

This is an automated alert from the DengueWatch SG.

The dengue risk level in your subscribed area ({planning_area}) is currently classified as {risk_level}. 

Please take immediate precautions to protect yourself and your community. We recommend practicing the 5-step 'Mozzie Wipeout':
1. Turn the pail
2. Tip the vase
3. Flip the flowerpot plate
4. Loosen the hardened soil
5. Clear the roof gutter and place BTI insecticide

Apply insect repellent when heading outdoors and wear long, covered clothing if possible.

To unsubscribe from alerts for {planning_area}, please visit: {unsubscribe_link}

Stay safe,
DengueWatch SG
"""

ALERT_BODY_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
    <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #d9534f; color: white; padding: 20px; text-align: center;">
            <h2 style="margin: 0;">🚨 Dengue Risk Alert</h2>
        </div>
        <div style="padding: 20px;">
            <p>Hello,</p>
            <p>This is an automated alert from the DengueWatch SG.</p>
            <p>The dengue risk level in your subscribed area (<strong>{planning_area}</strong>) is currently classified as <strong style="color: #d9534f;">{risk_level}</strong>.</p>
            
            <h3 style="color: #d9534f; border-bottom: 1px solid #ddd; padding-bottom: 5px;">Take Action: The Mozzie Wipeout</h3>
            <ul style="padding-left: 20px;">
                <li><strong>Turn</strong> the pail</li>
                <li><strong>Tip</strong> the vase</li>
                <li><strong>Flip</strong> the flowerpot plate</li>
                <li><strong>Loosen</strong> the hardened soil</li>
                <li><strong>Clear</strong> the roof gutter and place BTI insecticide</li>
            </ul>
            
            <p style="background-color: #f9f9f9; padding: 10px; border-left: 4px solid #f0ad4e;">
                <em>Tip: Apply insect repellent when heading outdoors and wear long, covered clothing if possible.</em>
            </p>
            
            <p style="margin-top: 30px; font-size: 0.9em; color: #777; border-top: 1px solid #ddd; padding-top: 10px;">
                To unsubscribe from alerts for <strong>{planning_area}</strong>, <a href="{unsubscribe_link}" style="color: #d9534f;">click here</a>.
            </p>
            
            <p>Stay safe,<br><strong>DengueWatch SG</strong></p>
        </div>
    </div>
</body>
</html>
"""
