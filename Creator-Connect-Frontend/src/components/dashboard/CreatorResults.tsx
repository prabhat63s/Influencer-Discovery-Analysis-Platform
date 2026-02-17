"use client"

import { motion, Variants } from "framer-motion"
import { BadgeCheck, Heart, MessageCircle } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { ProfileCardProps } from "@/types/creator.types"
import { Skeleton } from "@/components/ui/skeleton"
interface CreatorResultsProps extends ProfileCardProps {
    isLoading?: boolean;
}

const CreatorResults = ({ onViewProfile, creators, isLoading }: CreatorResultsProps) => {
    const containerVariants: Variants = {
        hidden: { opacity: 0 },
        visible: {
            opacity: 1,
            transition: {
                staggerChildren: 0.1
            }
        }
    };

    // Helper to proxy image URLs
    const getProxyUrl = (url?: string) => {
        if (!url) return "";
        if (url.startsWith("data:")) return url;
        if (url.startsWith("http")) {
            // Check if already proxied
            if (url.includes("/api/proxy/image")) return url;

            const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
            return `${apiUrl}/api/proxy/image?url=${encodeURIComponent(url)}`;
        }
        return url;
    };

    // Helper to safely parse metrics
    const parseMetric = (value: unknown): number => {
        if (typeof value === 'number') return isNaN(value) ? 0 : value;
        if (typeof value === 'string') {
            const clean = value.replace(/,/g, '').replace(/[^0-9.\-]/g, '');
            const num = parseFloat(clean);
            return isNaN(num) ? 0 : num;
        }
        return 0;
    };

    return (
        <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="flex flex-col gap-6 w-full"
        >
            {isLoading ? (
                // Skeleton Loading State
                Array.from({ length: 3 }).map((_, idx) => (
                    <div
                        key={`skeleton-${idx}`}
                        className="bg-white/95 dark:bg-black/90 border w-full rounded-xl overflow-hidden shadow-xs p-6"
                    >
                        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
                            {/* Profile Info Skeleton */}
                            <div className="flex items-center gap-5 min-w-[240px]">
                                <Skeleton className="w-14 h-14 rounded-full" />
                                <div className="space-y-2">
                                    <Skeleton className="h-5 w-32" />
                                    <Skeleton className="h-4 w-24" />
                                </div>
                            </div>

                            {/* Stats Skeleton */}
                            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4 md:gap-2 flex-1 w-full md:w-auto">
                                {[...Array(5)].map((_, i) => (
                                    <div key={i} className="space-y-2">
                                        <Skeleton className="h-5 w-16" />
                                        <Skeleton className="h-3 w-12" />
                                    </div>
                                ))}
                            </div>

                            {/* Button Skeleton */}
                            <Skeleton className="h-10 w-32 rounded-lg" />
                        </div>

                        {/* Content Grid Skeleton */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                            {[...Array(4)].map((_, i) => (
                                <Skeleton key={i} className="aspect-square rounded-lg" />
                            ))}
                        </div>
                    </div>
                ))
            ) : (
                creators?.map((creator, index) => {
                    // Fallback logic for raw API data
                    const avatar = getProxyUrl(creator.avatar || creator.profile_pic_url || creator.PROFILE_PIC_URL);
                    const name = creator.name || creator.NAME || "Unknown";
                    const handle = creator.Id || creator.id || creator.username || "unknown";
                    const niche = creator.niche || creator.NICHE || "General";
                    const location = creator.location || creator.LOCATION || "Unknown";
                    const verified = creator.verified || creator.is_verified || false;

                    const followers = creator.stats?.followers || creator.followers || creator.metrics?.followers || "0";
                    const engagement = creator.stats?.engagement || creator.engagement_rate || creator.metrics?.engagement_rate || "0%";
                    const postsCount = creator.stats?.posts || creator.posts_count || creator.metrics?.posts_count || "0";

                    const recentContent = creator.recentContent || creator.posts || [];

                    // Safe values for display
                    const safeFollowers = parseMetric(followers);
                    const safeEngagement = parseMetric(engagement);

                    const displayFollowers = safeFollowers > 1000
                        ? (safeFollowers / 1000).toFixed(1) + 'K'
                        : safeFollowers.toLocaleString();

                    const displayEngagement = safeEngagement.toFixed(2) + '%';


                    return (
                        <motion.div
                            key={creator.id || creator.handle || index}
                            className="group relative bg-white/95 dark:bg-black/90 border w-full rounded-xl overflow-hidden shadow-xs hover:shadow-md transition-all duration-300"
                        >
                            <div className="p-6 relative z-10">
                                {/* Header Section */}
                                <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">

                                    {/* Profile Info */}
                                    <div className="flex items-center gap-5 min-w-[240px]">
                                        <div className="relative group-hover:scale-105 transition-transform duration-300">
                                            <div className="absolute inset-0 rounded-full opacity-0" />
                                            <Avatar className="w-14 h-14 border-2 border-transparent shadow-sm relative z-10">
                                                <AvatarImage src={avatar} className="object-cover" />
                                                <AvatarFallback className="text-xl font-bold bg-linear-to-br from-gray-100 to-gray-200 text-gray-700">{name[0]}</AvatarFallback>
                                            </Avatar>
                                            {verified && (
                                                <div className="absolute -bottom-1 -right-1 z-20 bg-background rounded-full p-0.5 shadow-sm">
                                                    <BadgeCheck className="w-5 h-5 fill-blue-500 text-white" />
                                                </div>
                                            )}
                                        </div>
                                        <div className="">
                                            <h3 className="font-bold text-lg tracking-tight text-foreground group-hover:text-primary transition-colors duration-300 flex items-center gap-2">
                                                {name}
                                            </h3>
                                            <p className="text-muted-foreground font-medium text-sm">@{handle}</p>
                                        </div>
                                    </div>

                                    {/* Stats */}
                                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4 md:gap-2 flex-1 w-full md:w-auto">
                                        <div className="text-left">
                                            <p className="font-semibold text-lg tracking-tight text-foreground">
                                                {displayFollowers}
                                            </p>
                                            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mt-0.5">Followers</p>
                                        </div>
                                        <div className="text-left">
                                            <p className="font-semibold text-lg tracking-tight text-foreground">
                                                {displayEngagement}
                                            </p>
                                            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mt-0.5">Engagement</p>
                                        </div>
                                        <div className="text-left">
                                            <p className="font-semibold text-lg tracking-tight text-foreground">{String(location ?? '')}</p>
                                            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mt-0.5">Location</p>
                                        </div>
                                        <div className="text-left">
                                            <p className="font-semibold text-lg tracking-tight text-foreground">{String(postsCount ?? '')}</p>
                                            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mt-0.5">Posts</p>
                                        </div>
                                        <div className="text-left col-span-2 sm:col-span-1">
                                            <p className="font-semibold text-lg tracking-tight text-foreground">{String(niche ?? '')}</p>
                                            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mt-0.5">Niche</p>
                                        </div>
                                    </div>

                                    {(creator.id || creator.Id) && (
                                        <Button
                                            className="font-medium rounded-lg px-6 h-10 w-full md:w-auto bg-linear-to-r from-pink-500/95 to-purple-600/95 text-white shadow-sm hover:opacity-90 transition-all duration-200"
                                            onClick={() => onViewProfile(creator)}
                                        >
                                            View Profile
                                        </Button>
                                    )}
                                </div>

                                {/* Content Grid */}
                                {recentContent && recentContent.length > 0 && (
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                                        {recentContent.slice(0, 4).map((content: Record<string, unknown>, idx: number) => {
                                            const contentUrl = getProxyUrl((content.image_url || content.url || content.thumbnail_url) as string);
                                            const likes = parseMetric(content.likes ?? content.like_count);
                                            const comments = parseMetric(content.comments ?? content.comment_count);

                                            // Handle case where imageUrl is missing
                                            if (!contentUrl) {
                                                return (
                                                    <div key={idx} className="aspect-square rounded-lg flex items-center justify-center bg-muted/50 border border-border/50">
                                                        <span className="text-xs text-muted-foreground">No Media</span>
                                                    </div>
                                                )
                                            }

                                            return (
                                                <div key={idx} className="aspect-square rounded-lg overflow-hidden relative group/image cursor-pointer bg-muted/20 border border-border/50">
                                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                                    <img
                                                        src={contentUrl}
                                                        alt={`Post ${idx + 1}`}
                                                        className="w-full h-full object-cover transition-transform duration-700 group-hover/image:scale-110"
                                                    /* eslint-disable-next-line @next/next/no-img-element */
                                                    />
                                                    <div className="absolute inset-0 bg-linear-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover/image:opacity-100 transition-all duration-300 flex flex-col justify-end p-4">
                                                        <div className="flex items-center justify-center gap-2 text-white font-bold translate-y-4 group-hover/image:translate-y-0 transition-transform duration-300">
                                                            <div className="flex items-center gap-1.5 backdrop-blur-md bg-white/20 px-2 py-1 rounded-full">
                                                                <Heart className="w-3.5 h-3.5 fill-white text-white" />
                                                                <span className="text-xs">{likes > 1000 ? (likes / 1000).toFixed(1) + 'k' : likes}</span>
                                                            </div>
                                                            <div className="flex items-center gap-1.5 backdrop-blur-md bg-white/20 px-2 py-1 rounded-full">
                                                                <MessageCircle className="w-3.5 h-3.5 fill-white" />
                                                                <span className="text-xs">{comments > 1000 ? (comments / 1000).toFixed(1) + 'k' : comments}</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    );
                }))}
        </motion.div>
    )
}

export default CreatorResults
