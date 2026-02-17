"use client";

import { motion } from "framer-motion";
import { BadgeCheck, Download, ExternalLink, Facebook, Instagram, Loader2, MapPin, Twitter, Youtube } from "lucide-react";
import Image from "next/image";
import { ComponentType } from "react";

type CreatorProfileCardProps = {
    profileImage?: string | null;
    name: string;
    username?: string | null;
    niche?: string | null;
    location?: string | null;
    biography?: string | null;
    profileLink?: string | null;
    externalUrl?: string | string[] | null;
    isVerified?: boolean;
    onDownloadPdf?: () => void;
    pdfLoading?: boolean;
};

const platformIcons: Record<string, ComponentType<{ size?: number; className?: string }>> = {
    youtube: Youtube,
    twitter: Twitter,
    facebook: Facebook,
    website: ExternalLink,
};

const detectPlatform = (url: string): string => {
    if (!url) return "website";
    const u = url.toLowerCase();
    if (u.includes("instagram.com")) return "instagram";
    if (u.includes("youtube.com") || u.includes("youtu.be")) return "youtube";
    if (u.includes("twitter.com") || u.includes("x.com")) return "twitter";
    if (u.includes("facebook.com")) return "facebook";
    if (u.includes("tiktok.com")) return "tiktok";
    return "website";
};

const getInitials = (name: string): string => {
    if (!name) return "?";
    const parts = name.trim().split(" ");
    if (parts.length === 1) return parts[0][0].toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
};

export default function CreatorProfileCard({
    profileImage,
    name,
    username,
    niche,
    location,
    biography,
    profileLink,
    externalUrl,
    isVerified,
    onDownloadPdf,
    pdfLoading,
}: CreatorProfileCardProps) {
    // Extract external links
    const externalLinks: string[] = (() => {
        if (!externalUrl) return [];
        if (Array.isArray(externalUrl)) return externalUrl.filter((u): u is string => typeof u === "string" && u.trim().length > 0);
        if (typeof externalUrl === "string" && externalUrl.trim() && externalUrl !== "nan" && externalUrl !== "N/A") {
            return [externalUrl.trim()];
        }
        return [];
    })();

    const displayBio = biography && biography !== "nan" && biography !== "N/A" ? biography : null;

    return (
        <div className="h-full">
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="h-full bg-white dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm p-6 relative overflow-hidden group"
            >
                {/* Subtle decorative gradient */}
                <div className="absolute top-0 right-0 p-16 bg-linear-to-br from-purple-500/5 to-pink-500/5 blur-3xl rounded-full -translate-y-1/2 translate-x-1/2 pointer-events-none" />

                <div className="relative z-10 flex flex-col h-full">
                    {/* Header: Avatar + Meta */}
                    <div className="flex flex-col sm:flex-row gap-5 items-start">
                        <div className="relative shrink-0">
                            {profileImage ? (
                                <div className="relative rounded-full p-1 bg-linear-to-br from-purple-100 to-pink-100 dark:from-purple-900/30 dark:to-pink-900/30">
                                    <Image
                                        src={profileImage}
                                        alt={name}
                                        width={96}
                                        height={96}
                                        className="w-24 h-24 rounded-full object-cover border-4 border-white dark:border-[#1a1a1a] shadow-md"
                                    />
                                    {isVerified && (
                                        <div className="absolute bottom-1 right-1 bg-white dark:bg-[#1a1a1a] rounded-full p-1 shadow-sm">
                                            <BadgeCheck className="w-5 h-5 text-blue-500" fill="currentColor" size={20} />
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="w-24 h-24 rounded-full bg-linear-to-br from-purple-500 to-pink-600 flex items-center justify-center text-white text-3xl font-bold shadow-lg">
                                    {getInitials(name)}
                                </div>
                            )}
                        </div>

                        <div className="flex-1 min-w-0 pt-1">
                            <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate leading-tight tracking-tight">
                                {name}
                            </h1>
                            {username && (
                                <p className="text-gray-500 dark:text-gray-400 font-medium mb-2">@{username}</p>
                            )}

                            <div className="flex flex-wrap gap-2 mt-1">
                                {niche && (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-50 text-purple-700 dark:bg-purple-500/10 dark:text-purple-300 border border-purple-100 dark:border-purple-500/20">
                                        {niche}
                                    </span>
                                )}
                                {location && (
                                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-300 border border-gray-100 dark:border-gray-700">
                                        <MapPin size={12} />
                                        {location}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Bio */}
                    {displayBio && (
                        <div className="mt-6">
                            <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed line-clamp-4">
                                {displayBio}
                            </p>
                        </div>
                    )}

                    {/* Spacer to push socials to bottom if flex-col */}
                    <div className="flex-1" />

                    {/* Social Links & Actions */}
                    <div className="mt-6 pt-6 border-t border-gray-100 dark:border-white/5 flex flex-col sm:flex-row md:items-center items-start justify-between gap-4">
                        <div className="flex gap-2 flex-wrap">
                            {profileLink && (
                                <SocialButton href={profileLink} icon={Instagram} label="Instagram" className="text-pink-600 bg-pink-50 hover:bg-pink-100 dark:bg-pink-900/20 dark:hover:bg-pink-900/40" />
                            )}
                            {externalLinks.map((url, idx) => {
                                const platform = detectPlatform(url);
                                const Icon = platform === "instagram" ? Instagram : platformIcons[platform] || ExternalLink;
                                return (
                                    <SocialButton
                                        key={idx}
                                        href={url}
                                        icon={Icon}
                                        label={platform}
                                        className="text-gray-600 bg-gray-50 hover:bg-gray-100 dark:text-gray-300 dark:bg-white/5 dark:hover:bg-white/10"
                                    />
                                );
                            })}
                        </div>

                        <div className="w-full sm:w-auto flex flex-col sm:flex-row gap-3">
                            {onDownloadPdf && (
                                <button
                                    onClick={onDownloadPdf}
                                    disabled={pdfLoading}
                                    className="w-full sm:w-auto text-sm flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-gray-900 dark:bg-white text-white dark:text-gray-900 font-medium hover:bg-gray-800 dark:hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.98] shadow-sm hover:shadow-md"
                                >
                                    {pdfLoading ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <Download className="w-4 h-4" />
                                    )}
                                    {pdfLoading ? "Generating..." : "Download PDF"}
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}

function SocialButton({ href, icon: Icon, className, label }: { href: string; icon: ComponentType<{ size?: number }>; className?: string; label: string }) {
    return (
        <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={`p-2.5 rounded-xl transition-all duration-200 hover:scale-105 active:scale-95 flex items-center justify-center ${className}`}
            title={label}
        >
            <Icon size={18} />
        </a>
    )
}
