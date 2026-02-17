"use client";

import { motion } from "framer-motion";
import { Crown, Heart, MessageCircle, Minus, Shield, TrendingDown, TrendingUp, Users } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

type InfluencerData = {
    id?: string;
    NAME?: string;
    name?: string;
    Id?: string;
    username?: string;
    profile_link?: string;
    PROFILE_LINK?: string;
    followers?: string | number;
    engagement_rate?: string | number;
    real_percentage?: string | number;
    real_followers_percentage?: string | number;
    average_likes?: string | number;
    avg_likes?: string | number;
    average_comments?: string | number;
    avg_comments?: string | number;
    industry_anchor?: boolean;
    industry_standard?: boolean;
    profile_pic_url?: string;
    profile_image?: string;
    image?: string;
    NICHE?: string;
    niche?: string;
};

type IndustryStandardComparisonProps = {
    anchor: InfluencerData;
    peers: InfluencerData[];
    isLoadingMore?: boolean;
    isInternalComparison?: boolean;
    // Profession Peers Support (Top Searches) - Toggle now controlled from parent
    professionPeers?: InfluencerData[];
    professionPeersStatus?: "not_started" | "processing" | "completed";
    comparisonMode?: "internal" | "profession";
    // onModeChange is removed - toggle is now in the page header
};

const parseNumericValue = (value: unknown): number => {
    if (typeof value === "number") return value;
    if (typeof value === "string") {
        const trimmed = value.trim().toUpperCase();
        if (!trimmed || trimmed === "N/A" || trimmed === "NAN" || trimmed === "NULL" || trimmed === "UNDEFINED") {
            return 0;
        }
        const cleaned = value.replace(/[,]/g, "").trim();
        const num = parseFloat(cleaned.replace(/[KkMm]/g, ""));
        if (isNaN(num)) return 0;
        const str = String(value).toUpperCase();
        if (str.includes("M")) return num * 1_000_000;
        if (str.includes("K")) return num * 1_000;
        return num;
    }
    return 0;
};

const formatNumber = (value: number): string => {
    if (isNaN(value) || !isFinite(value)) return "N/A";
    if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
    return value.toLocaleString();
};

export default function IndustryStandardComparison({
    anchor,
    peers: explicitPeers,
    isLoadingMore,
    professionPeers,
    comparisonMode = "internal",
}: IndustryStandardComparisonProps) {

    // Choose peers based on active mode
    const activePeers = (comparisonMode === "profession" && professionPeers && professionPeers.length > 0)
        ? professionPeers
        : explicitPeers;

    // Combine anchor + peers (max 3 total)
    const allInfluencers = [anchor, ...activePeers.slice(0, 2)];

    if (allInfluencers.length < 2) {
        return null;
    }

    // Calculate all comparison metrics for each influencer
    const influencerData = allInfluencers.map((inf, originalIndex) => ({
        username: (inf.Id || inf.id || inf.username || inf.NAME || inf.name || "Unknown") as string,
        displayName: (inf.NAME || inf.name || inf.Id || inf.username || "Unknown") as string,
        followers: parseNumericValue(inf.followers),
        engagementRate: parseNumericValue(inf.engagement_rate),
        realFollowersPct: parseNumericValue(inf.real_percentage || inf.real_followers_percentage),
        avgLikes: parseNumericValue(inf.avg_likes || inf.average_likes),
        avgComments: parseNumericValue(inf.avg_comments || inf.average_comments),
        isAnchor: originalIndex === 0, // First one is always the anchor
        originalOrder: originalIndex,
    }));

    // Sort by followers for ranking
    const sortedByFollowers = [...influencerData].sort((a, b) => b.followers - a.followers);

    const maxFollowers = Math.max(...influencerData.map(inf => inf.followers), 1);
    const maxEngagementRate = Math.max(...influencerData.map(inf => inf.engagementRate), 1);
    const maxRealFollowersPct = Math.max(...influencerData.map(inf => inf.realFollowersPct), 1);
    const maxAvgLikes = Math.max(...influencerData.map(inf => inf.avgLikes), 1);
    const maxAvgComments = Math.max(...influencerData.map(inf => inf.avgComments), 1);

    // Assign ranks and colors based on followers
    const rankedData = influencerData.map(inf => {
        const rank = sortedByFollowers.findIndex(s => s.username === inf.username) + 1;
        let color = "#dc2626"; // Red (3rd)
        let bgColor = "bg-red-50 dark:bg-red-900/20";
        let borderColor = "border-red-200 dark:border-red-800";
        let icon: "up" | "down" | "mid" = "down";

        if (rank === 1) {
            color = "#16a34a"; // Green
            bgColor = "bg-green-50 dark:bg-green-900/20";
            borderColor = "border-green-200 dark:border-green-800";
            icon = "up";
        } else if (rank === 2) {
            color = "#eab308"; // Yellow
            bgColor = "bg-yellow-50 dark:bg-yellow-900/20";
            borderColor = "border-yellow-200 dark:border-yellow-800";
            icon = "mid";
        }

        return {
            ...inf,
            rank,
            color,
            bgColor,
            borderColor,
            icon,
            followersPercentage: (inf.followers / maxFollowers) * 100,
            engagementRatePercentage: (inf.engagementRate / maxEngagementRate) * 100,
            realFollowersPctPercentage: (inf.realFollowersPct / maxRealFollowersPct) * 100,
            avgLikesPercentage: (inf.avgLikes / maxAvgLikes) * 100,
            avgCommentsPercentage: (inf.avgComments / maxAvgComments) * 100,
        };
    });

    // Sort by rank for display
    const sortedRankedData = [...rankedData].sort((a, b) => a.rank - b.rank);

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white dark:bg-neutral-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-lg overflow-hidden"
        >
            {/* Header */}
            <div className="p-6 border-b border-gray-200 dark:border-gray-800">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                    {comparisonMode === "profession" ? "Industry Standard Benchmark" : "Search Results Comparison"}
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                    {comparisonMode === "profession"
                        ? `Comparing against industry peers with ~5x followers`
                        : `Comparing ${allInfluencers.length} search results against each other`}
                </p>
            </div>

            {/* RANKING SECTION - Prominently displayed at the top */}
            <div className="p-6 bg-linear-to-r from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 border-b border-gray-200 dark:border-gray-800">
                <div className="flex items-center gap-2 mb-4">
                    <Crown className="w-5 h-5 text-amber-500" />
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Overall Ranking</h3>
                </div>
                <div className="flex flex-wrap gap-4 justify-center">
                    {sortedRankedData.map((inf, idx) => (
                        <motion.div
                            key={inf.username}
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: idx * 0.1 }}
                            className={`flex-1 min-w-[200px] max-w-[300px] ${inf.bgColor} ${inf.borderColor} border rounded-xl p-4 text-center shadow-sm`}
                        >
                            <div className="flex items-center justify-center gap-2 mb-2">
                                {inf.rank === 1 && <Crown className="w-6 h-6 text-amber-500" />}
                                <span
                                    className="text-3xl font-bold"
                                    style={{ color: inf.color }}
                                >
                                    {inf.rank === 1 ? "1st" : inf.rank === 2 ? "2nd" : "3rd"}
                                </span>
                            </div>
                            <p className="font-semibold text-gray-900 dark:text-white truncate">
                                {inf.displayName}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                @{inf.username}
                            </p>
                            {inf.isAnchor && (
                                <span className="inline-block mt-2 text-xs px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300 font-medium">
                                    Anchor
                                </span>
                            )}
                        </motion.div>
                    ))}
                </div>
            </div>

            {/* METRICS SECTIONS - Similar to DashboardMetrics */}
            <div className="space-y-0">

                {/* 1. FOLLOWERS METRIC */}
                <div className="p-6 border-b border-gray-200 dark:border-gray-800">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 rounded-full bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
                            <Users className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        </div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Followers</h3>
                    </div>

                    <div className="space-y-3">
                        {sortedRankedData.map((inf, idx) => (
                            <motion.div
                                key={`followers-${inf.username}`}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: idx * 0.1 }}
                                className="flex items-center gap-4"
                            >
                                <div className="flex items-center gap-2 min-w-[140px]">
                                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: inf.color }} />
                                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                                        @{inf.username}
                                    </span>
                                    {inf.isAnchor && (
                                        <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300">
                                            Anchor
                                        </span>
                                    )}
                                </div>
                                <div className="flex-1">
                                    <div className="relative w-full h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                        <motion.div
                                            initial={{ width: 0 }}
                                            animate={{ width: `${inf.followersPercentage}%` }}
                                            transition={{ duration: 0.8, delay: idx * 0.1 }}
                                            className="h-full rounded-full"
                                            style={{ backgroundColor: inf.color }}
                                        />
                                    </div>
                                </div>
                                <div className="min-w-[80px] text-right">
                                    <span className="text-lg font-bold text-gray-900 dark:text-white">
                                        {formatNumber(inf.followers)}
                                    </span>
                                </div>
                                <div className="w-6">
                                    {inf.icon === "up" && <TrendingUp size={18} className="text-green-600" />}
                                    {inf.icon === "mid" && <Minus size={18} className="text-yellow-600" />}
                                    {inf.icon === "down" && <TrendingDown size={18} className="text-red-600" />}
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>

                {/* 2. ENGAGEMENT RATE METRIC */}
                <div className="p-6 border-b border-gray-200 dark:border-gray-800">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 rounded-full bg-pink-100 dark:bg-pink-900/30 flex items-center justify-center">
                            <TrendingUp className="w-5 h-5 text-pink-600 dark:text-pink-400" />
                        </div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Engagement Rate</h3>
                    </div>

                    <div className="space-y-3">
                        {[...rankedData].sort((a, b) => b.engagementRate - a.engagementRate).map((inf, idx) => {
                            const engagementRank = idx + 1;
                            const engagementColor = engagementRank === 1 ? "#16a34a" : engagementRank === 2 ? "#eab308" : "#dc2626";

                            return (
                                <motion.div
                                    key={`engagement-${inf.username}`}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.1 }}
                                    className="flex items-center gap-4"
                                >
                                    <div className="flex items-center gap-2 min-w-[140px]">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: engagementColor }} />
                                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                                            @{inf.username}
                                        </span>
                                        {inf.isAnchor && (
                                            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300">
                                                Anchor
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex-1">
                                        <div className="relative w-full h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${inf.engagementRatePercentage}%` }}
                                                transition={{ duration: 0.8, delay: idx * 0.1 }}
                                                className="h-full rounded-full"
                                                style={{ backgroundColor: engagementColor }}
                                            />
                                        </div>
                                    </div>
                                    <div className="min-w-[80px] text-right">
                                        <span className="text-lg font-bold text-gray-900 dark:text-white">
                                            {inf.engagementRate > 0 ? `${inf.engagementRate.toFixed(2)}%` : "N/A"}
                                        </span>
                                    </div>
                                    <div className="w-6">
                                        <span className="text-xs font-bold px-1.5 py-0.5 rounded" style={{ backgroundColor: `${engagementColor}20`, color: engagementColor }}>
                                            {engagementRank === 1 ? "1st" : engagementRank === 2 ? "2nd" : "3rd"}
                                        </span>
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>

                {/* 3. AUDIENCE AUTHENTICITY METRIC */}
                <div className="p-6 border-b border-gray-200 dark:border-gray-800">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                            <Shield className="w-5 h-5 text-green-600 dark:text-green-400" />
                        </div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Audience Authenticity</h3>
                    </div>

                    <div className="space-y-3">
                        {[...rankedData].sort((a, b) => b.realFollowersPct - a.realFollowersPct).map((inf, idx) => {
                            const authRank = idx + 1;
                            const authColor = authRank === 1 ? "#16a34a" : authRank === 2 ? "#eab308" : "#dc2626";

                            return (
                                <motion.div
                                    key={`auth-${inf.username}`}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.1 }}
                                    className="flex items-center gap-4"
                                >
                                    <div className="flex items-center gap-2 min-w-[140px]">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: authColor }} />
                                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                                            @{inf.username}
                                        </span>
                                        {inf.isAnchor && (
                                            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300">
                                                Anchor
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex-1">
                                        <div className="relative w-full h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${inf.realFollowersPctPercentage}%` }}
                                                transition={{ duration: 0.8, delay: idx * 0.1 }}
                                                className="h-full rounded-full"
                                                style={{ backgroundColor: authColor }}
                                            />
                                        </div>
                                    </div>
                                    <div className="min-w-[80px] text-right">
                                        <span className="text-lg font-bold text-gray-900 dark:text-white">
                                            {inf.realFollowersPct > 0 ? `${inf.realFollowersPct.toFixed(1)}%` : "N/A"}
                                        </span>
                                    </div>
                                    <div className="w-6">
                                        <span className="text-xs font-bold px-1.5 py-0.5 rounded" style={{ backgroundColor: `${authColor}20`, color: authColor }}>
                                            {authRank === 1 ? "1st" : authRank === 2 ? "2nd" : "3rd"}
                                        </span>
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>

                {/* 4. AVERAGE LIKES METRIC */}
                <div className="p-6 border-b border-gray-200 dark:border-gray-800">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                            <Heart className="w-5 h-5 text-red-600 dark:text-red-400" />
                        </div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Average Likes</h3>
                    </div>

                    <div className="space-y-3">
                        {[...rankedData].sort((a, b) => b.avgLikes - a.avgLikes).map((inf, idx) => {
                            const likesRank = idx + 1;
                            const likesColor = likesRank === 1 ? "#16a34a" : likesRank === 2 ? "#eab308" : "#dc2626";

                            return (
                                <motion.div
                                    key={`likes-${inf.username}`}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.1 }}
                                    className="flex items-center gap-4"
                                >
                                    <div className="flex items-center gap-2 min-w-[140px]">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: likesColor }} />
                                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                                            @{inf.username}
                                        </span>
                                        {inf.isAnchor && (
                                            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300">
                                                Anchor
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex-1">
                                        <div className="relative w-full h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${inf.avgLikesPercentage}%` }}
                                                transition={{ duration: 0.8, delay: idx * 0.1 }}
                                                className="h-full rounded-full"
                                                style={{ backgroundColor: likesColor }}
                                            />
                                        </div>
                                    </div>
                                    <div className="min-w-[80px] text-right">
                                        <span className="text-lg font-bold text-gray-900 dark:text-white">
                                            {inf.avgLikes > 0 ? formatNumber(inf.avgLikes) : "N/A"}
                                        </span>
                                    </div>
                                    <div className="w-6">
                                        <span className="text-xs font-bold px-1.5 py-0.5 rounded" style={{ backgroundColor: `${likesColor}20`, color: likesColor }}>
                                            {likesRank === 1 ? "1st" : likesRank === 2 ? "2nd" : "3rd"}
                                        </span>
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>

                {/* 5. AVERAGE COMMENTS METRIC */}
                <div className="p-6">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                            <MessageCircle className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Average Comments</h3>
                    </div>

                    <div className="space-y-3">
                        {[...rankedData].sort((a, b) => b.avgComments - a.avgComments).map((inf, idx) => {
                            const commentsRank = idx + 1;
                            const commentsColor = commentsRank === 1 ? "#16a34a" : commentsRank === 2 ? "#eab308" : "#dc2626";

                            return (
                                <motion.div
                                    key={`comments-${inf.username}`}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.1 }}
                                    className="flex items-center gap-4"
                                >
                                    <div className="flex items-center gap-2 min-w-[140px]">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: commentsColor }} />
                                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                                            @{inf.username}
                                        </span>
                                        {inf.isAnchor && (
                                            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300">
                                                Anchor
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex-1">
                                        <div className="relative w-full h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${inf.avgCommentsPercentage}%` }}
                                                transition={{ duration: 0.8, delay: idx * 0.1 }}
                                                className="h-full rounded-full"
                                                style={{ backgroundColor: commentsColor }}
                                            />
                                        </div>
                                    </div>
                                    <div className="min-w-[80px] text-right">
                                        <span className="text-lg font-bold text-gray-900 dark:text-white">
                                            {inf.avgComments > 0 ? formatNumber(inf.avgComments) : "N/A"}
                                        </span>
                                    </div>
                                    <div className="w-6">
                                        <span className="text-xs font-bold px-1.5 py-0.5 rounded" style={{ backgroundColor: `${commentsColor}20`, color: commentsColor }}>
                                            {commentsRank === 1 ? "1st" : commentsRank === 2 ? "2nd" : "3rd"}
                                        </span>
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Loading indicator for additional peers */}
            {isLoadingMore && (
                <div className="p-6 border-t border-gray-200 dark:border-gray-800">
                    <div className="flex items-center gap-4 animate-pulse">
                        <div className="flex items-center gap-2 min-w-[140px]">
                            <Skeleton className="w-3 h-3 rounded-full" />
                            <Skeleton className="h-4 w-24 rounded" />
                        </div>
                        <div className="flex-1">
                            <Skeleton className="h-4 w-full rounded-full" />
                        </div>
                        <div className="min-w-[80px]">
                            <Skeleton className="h-6 w-16 ml-auto rounded" />
                        </div>
                        <div className="w-6">
                            <Skeleton className="h-4 w-4 rounded-full" />
                        </div>
                    </div>
                </div>
            )}
        </motion.div>
    );
}
