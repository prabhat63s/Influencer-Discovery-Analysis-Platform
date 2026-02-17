"use client";

import { motion } from "framer-motion";
import { FileText, Heart, Info, MessageCircle, TrendingUp, UserCheck, Users } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

type InfluencerInfoCardProps = {
    followers?: number;
    following?: number;
    engagementRate?: number;
    realFollowersPct?: number;
    suspiciousFollowers?: number;
    avgLikes?: number;
    avgComments?: number;
    posts?: number;
};

const formatNumber = (num: number): string => {
    if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + "M";
    if (num >= 1_000) return (num / 1_000).toFixed(1) + "K";
    return num.toFixed(0);
};

export default function InfluencerInfoCard({
    followers = 0,
    following = 0,
    engagementRate = 0,
    avgLikes = 0,
    avgComments = 0,
    posts = 0,
}: InfluencerInfoCardProps) {

    // Data config for rendering
    const items = [
        {
            label: "Followers",
            value: formatNumber(followers),
            subtext: "Audience",
            icon: Users,
            description: "Total follower count represents potential reach.",
            colorClass: "text-purple-600 dark:text-purple-400",
            bgClass: "bg-purple-50 dark:bg-purple-900/20"
        },
        {
            label: "Engagement",
            value: `${engagementRate.toFixed(2)}%`,
            subtext: "Interaction",
            icon: TrendingUp,
            description: "Percentage of followers who actively interact with content.",
            colorClass: "text-green-600 dark:text-green-400",
            bgClass: "bg-green-50 dark:bg-green-900/20"
        },
        {
            label: "Following",
            value: formatNumber(following),
            subtext: "Accounts",
            icon: UserCheck,
            description: "Number of accounts this influencer follows.",
            colorClass: "text-blue-600 dark:text-blue-400",
            bgClass: "bg-blue-50 dark:bg-blue-900/20",
            hide: following === 0
        },
        {
            label: "Avg. Likes",
            value: formatNumber(avgLikes),
            subtext: "Per Post",
            icon: Heart,
            description: "Average number of likes per post.",
            colorClass: "text-pink-600 dark:text-pink-400",
            bgClass: "bg-pink-50 dark:bg-pink-900/20"
        },
        {
            label: "Avg. Comments",
            value: formatNumber(avgComments),
            subtext: "Per Post",
            icon: MessageCircle,
            description: "Average number of comments per post.",
            colorClass: "text-indigo-600 dark:text-indigo-400",
            bgClass: "bg-indigo-50 dark:bg-indigo-900/20"
        },
        {
            label: "Total Posts",
            value: formatNumber(posts),
            subtext: "Lifetime",
            icon: FileText,
            description: "Total number of posts published.",
            colorClass: "text-amber-600 dark:text-amber-400",
            bgClass: "bg-amber-50 dark:bg-amber-900/20"
        }
    ].filter(i => !i.hide);

    return (
        <TooltipProvider>
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.1 }}
                className="h-full bg-white dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm p-6"
            >
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        Performance Overview
                    </h2>
                    <span className="text-xs font-medium px-2 py-1 rounded bg-gray-100 dark:bg-white/10 text-gray-500 dark:text-gray-400">
                        Live Data
                    </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    {items.map((item, idx) => (
                        <motion.div
                            key={item.label}
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 0.1 + (idx * 0.05) }}
                            className="group p-4 rounded-xl bg-gray-50/50 dark:bg-white/5 border border-gray-100 dark:border-white/5 hover:border-gray-200 dark:hover:border-white/20 transition-all hover:shadow-sm"
                        >
                            <div className="flex items-start justify-between mb-3">
                                <div className={`p-2 rounded-lg ${item.bgClass} bg-opacity-50`}>
                                    <item.icon size={16} className={item.colorClass} />
                                </div>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Info size={14} className="text-gray-300 dark:text-gray-600 hover:text-gray-500 cursor-help" />
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p className="text-xs">{item.description}</p>
                                    </TooltipContent>
                                </Tooltip>
                            </div>

                            <div>
                                <div className="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">
                                    {item.value}
                                </div>
                                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-1">
                                    {item.label}
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </motion.div>
        </TooltipProvider>
    );
}
