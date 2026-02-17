
import { NextResponse } from 'next/server';
import nodemailer from 'nodemailer';
import { getAdminNotificationEmail, getUserConfirmationEmail } from '@/lib/email-templates';

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const { name, email } = body;

        if (!name || !email) {
            return NextResponse.json(
                { message: 'Name and email are required' },
                { status: 400 }
            );
        }

        // Configure Nodemailer transporter
        // NOTE: These environment variables need to be set in .env

        console.log("Debug: SMTP Config:", {
            host: process.env.SMTP_HOST,
            port: process.env.SMTP_PORT,
            secure: process.env.SMTP_SECURE,
            user: process.env.SMTP_USER,
            passLength: process.env.SMTP_PASS ? process.env.SMTP_PASS.length : 0
        });

        const transporter = nodemailer.createTransport({
            host: process.env.SMTP_HOST,
            port: Number(process.env.SMTP_PORT) || 587,
            secure: process.env.SMTP_SECURE === 'true', // true for 465, false for other ports
            auth: {
                user: process.env.SMTP_USER,
                pass: process.env.SMTP_PASS,
            },
        });

        // Verify connection configuration
        await new Promise((resolve, reject) => {
            transporter.verify(function (error, success) {
                if (error) {
                    console.error("Debug: Transporter Verification Error:", error);
                    reject(error);
                } else {
                    console.log("Debug: Server is ready to take our messages");
                    resolve(success);
                }
            });
        });

        // 1. Send Admin Notification
        const adminMailOptions = {
            from: process.env.SMTP_FROM || '"Creator Connect" <noreply@creatorconnect.com>',
            to: process.env.ADMIN_EMAIL || 'prabhat@gmail.com', // Replace with actual admin email
            subject: `New Demo Request: ${name}`,
            html: getAdminNotificationEmail(name, email),
            replyTo: email
        };

        // 2. Send User Confirmation
        const userMailOptions = {
            from: process.env.SMTP_FROM || '"Creator Connect" <noreply@creatorconnect.com>',
            to: email,
            subject: 'We Received Your Demo Request - Creator Connect',
            html: getUserConfirmationEmail(name),
        };

        // Send emails
        await Promise.all([
            transporter.sendMail(adminMailOptions),
            transporter.sendMail(userMailOptions)
        ]);

        return NextResponse.json(
            { message: 'Demo request sent successfully' },
            { status: 200 }
        );
    } catch (error) {
        console.error('Error sending email:', error);
        return NextResponse.json(
            { message: 'Failed to send demo request', error: (error as Error).message },
            { status: 500 }
        );
    }
}
