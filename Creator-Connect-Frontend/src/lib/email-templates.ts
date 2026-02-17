
export const getAdminNotificationEmail = (name: string, email: string) => `
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #f8f9fa; padding: 20px; text-align: center; border-bottom: 2px solid #e9ecef; }
        .content { padding: 30px 20px; background-color: #ffffff; }
        .field { margin-bottom: 15px; }
        .label { font-weight: bold; color: #666; font-size: 0.9em; text-transform: uppercase; }
        .value { font-size: 1.1em; color: #000; }
        .footer { text-align: center; margin-top: 30px; font-size: 0.8em; color: #999; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>New Demo Request</h2>
        </div>
        <div class="content">
            <p>You have received a new demo request from the Creator Connect website.</p>
            
            <div class="field">
                <div class="label">Name</div>
                <div class="value">${name}</div>
            </div>
            
            <div class="field">
                <div class="label">Email</div>
                <div class="value"><a href="mailto:${email}">${email}</a></div>
            </div>
            
            <div class="field">
                <div class="label">Time</div>
                <div class="value">${new Date().toLocaleString()}</div>
            </div>
        </div>
        <div class="footer">
            <p>This email was sent automatically from the Creator Connect contact form.</p>
        </div>
    </div>
</body>
</html>
`;

export const getUserConfirmationEmail = (name: string) => `
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #7c3aed; padding: 30px 20px; text-align: center; color: white; border-radius: 8px 8px 0 0; }
        .content { padding: 30px 20px; background-color: #ffffff; border: 1px solid #e9ecef; border-top: none; border-radius: 0 0 8px 8px; }
        .button { display: inline-block; padding: 12px 24px; background-color: #7c3aed; color: white; text-decoration: none; border-radius: 4px; font-weight: bold; margin-top: 20px; }
        .footer { text-align: center; margin-top: 30px; font-size: 0.8em; color: #999; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>We've Received Your Request!</h1>
        </div>
        <div class="content">
            <p>Hi ${name},</p>
            <p>Thanks for requesting a demo of Creator Connect. We're excited to show you how our platform can help you optimize your influencer marketing campaigns.</p>
            <p>Our team will review your request and get back to you within 24 hours to schedule a time that works best for you.</p>
            <p>In the meantime, feel free to explore our website for more resources.</p>
            
            <p>Best regards,<br>Creator Connect Team</p>
        </div>
        <div class="footer">
            <p>&copy; ${new Date().getFullYear()} Creator Connect . All rights reserved.</p>
        </div>
    </div>
</body>
</html>
`;
