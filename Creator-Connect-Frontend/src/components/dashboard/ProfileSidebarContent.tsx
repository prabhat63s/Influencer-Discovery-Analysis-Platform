
"use client"

import React from 'react'
import { motion } from "framer-motion"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

// Imported Visual Components
import CreatorProfileCard from '../CreatorProfileCard'
import InfluencerInfoCard from '../InfluencerInfoCard'
import IndustryStandardComparison from '../IndustryStandardComparison'
import DashboardMetrics from '../DashboardMetrics'
import AIInsight from '../AIInsight'
import PostAnalysisCard from './PostAnalysisCard'
import { CreatorProfile } from '@/types/creator.types'

interface ProfileSidebarContentProps {
    creator: Record<string, unknown> | null
    isLoading: boolean
    pdfLoading?: boolean
    onDownloadPdf?: () => void
    allResults?: Record<string, unknown>[]
    isPolling?: boolean
    metrics?: Record<string, unknown>
    detailedCreator?: Record<string, unknown>
}

// Helper types
type MetricsMap = Record<string, unknown>;

const ProfileSidebarContent = ({
    creator,
    isLoading,
    pdfLoading = false,
    onDownloadPdf,
    allResults = [],
    isPolling = false,
}: ProfileSidebarContentProps) => {

    if (!creator) return null;

    // Use detailed creator if available in prop (though passed as 'creator' here usually)
    const activeCreator = creator;

    // Data Normalization Helpers (Moved from original file)
    const safeString = (value: unknown): string | null =>
        typeof value === "string" && value.trim().length > 0 ? value : null;

    const formatLocation = (location: string | null): string | null => {
        if (!location) return null;
        let locStr = location.trim();
        try {
            const parsed = JSON.parse(locStr);
            if (typeof parsed === 'object' && parsed !== null) {
                if (Array.isArray(parsed) && parsed.length > 0) locStr = String(parsed[0]);
                else if (typeof parsed === 'object') locStr = parsed.city || parsed.name || parsed.location || locStr;
            }
        } catch { }
        locStr = locStr.replace(/["'\[\]]/g, '').replace(/location:/gi, '').trim();
        if (!locStr || locStr.toLowerCase() === 'n/a' || locStr.toLowerCase() === 'unknown' || locStr.toLowerCase() === 'global') return null;

        if (locStr.includes(',')) {
            const parts = locStr.split(',').map(p => p.trim()).filter(p => p);
            if (parts.length >= 2) locStr = parts.slice(0, 2).join(', ');
            else if (parts.length === 1) locStr = parts[0];
        }
        return locStr.length > 50 ? locStr.substring(0, 47) + '...' : locStr;
    };

    const normalizeNumericInput = (value: unknown): number => {
        if (value === null || value === undefined) return 0;
        if (typeof value === "number" && !Number.isNaN(value)) return value;
        if (typeof value === "string") {
            let sanitized = value.trim().replace(/,/g, "");
            if (!sanitized || sanitized.toLowerCase() === "n/a" || sanitized.toLowerCase() === "nan") return 0;
            let multiplier = 1;
            if (sanitized.endsWith("%")) sanitized = sanitized.slice(0, -1);
            const suffix = sanitized.slice(-1).toLowerCase();
            if (suffix === "k") { multiplier = 1_000; sanitized = sanitized.slice(0, -1); }
            else if (suffix === "m") { multiplier = 1_000_000; sanitized = sanitized.slice(0, -1); }
            const parsed = parseFloat(sanitized);
            return Number.isNaN(parsed) ? 0 : parsed * multiplier;
        }
        return 0;
    };

    const toPercent = (v: unknown): number => {
        if (v === null || v === undefined) return 0;
        if (typeof v === "number") {
            if (!Number.isFinite(v)) return 0;
            return Math.abs(v) <= 1 ? v : v;
        }
        if (typeof v === "string") {
            const s = v.trim().replace(/,/g, "").replace("%", "");
            if (!s || /^nan$/i.test(s) || /^n\/a$/i.test(s)) return 0;
            const n = Number(s);
            return Number.isNaN(n) ? 0 : Math.abs(n) <= 1 ? n : n;
        }
        return 0;
    };

    const hasMetricPayload = (payload: unknown): payload is MetricsMap => {
        if (!payload || typeof payload !== "object") return false;
        const keys = Object.keys(payload as Record<string, unknown>);
        if (!keys.length) return false;
        const signalKeys = ["followers", "avg_likes", "average_likes", "real_followers_percentage", "real_percentage"];
        return signalKeys.some((key) => key in payload);
    };

    const metrics: MetricsMap | null = (() => {
        if (hasMetricPayload(activeCreator.metrics)) return activeCreator.metrics;
        if (hasMetricPayload(activeCreator.raw_data)) return activeCreator.raw_data;
        if (hasMetricPayload(activeCreator)) return activeCreator;
        return null;
    })();

    const profileFollowers = normalizeNumericInput(metrics?.followers ?? activeCreator.followers ?? 0);
    const profileFollowing = normalizeNumericInput(metrics?.following ?? activeCreator.following ?? 0);
    const profileEngagementRate = toPercent(metrics?.engagement_rate ?? activeCreator.engagement_rate ?? 0);
    const profileAvgLikes = normalizeNumericInput(metrics?.avg_likes ?? metrics?.average_likes ?? activeCreator.avg_likes ?? activeCreator.average_likes ?? 0);
    const profileAvgComments = normalizeNumericInput(metrics?.avg_comments ?? metrics?.average_comments ?? activeCreator.avg_comments ?? activeCreator.average_comments ?? 0);
    const postsCount = normalizeNumericInput(metrics?.posts_count ?? metrics?.posts ?? activeCreator.posts_count ?? activeCreator.posts ?? 0);

    const influencerLocation = formatLocation(safeString(activeCreator.location));
    const isVerified = activeCreator.is_verified === true || activeCreator.verified === true;
    const derivedUsername = activeCreator.handle || activeCreator.username || "unknown";
    const realFollowersPct = toPercent(metrics?.real_percentage ?? metrics?.real_followers_percentage ?? activeCreator.real_percentage ?? activeCreator.real_followers_percentage ?? 0);
    const suspiciousFollowers = normalizeNumericInput(metrics?.suspicious_fake_followers ?? metrics?.suspicious_followers ?? activeCreator.suspicious_fake_followers ?? activeCreator.suspicious_followers ?? 0);

    const profileImage = activeCreator.avatar || activeCreator.profile_pic_url || activeCreator.PROFILE_PIC_URL || activeCreator.profile_image;


    if (isLoading) {
        return (
            <div className="space-y-8 animate-pulse">
                {/* 1. Top Section: Profile & Quick Stats Key Info Skeleton */}
                <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
                    <div className="md:col-span-5 space-y-6">
                        {/* Creator Profile Card Skeleton */}
                        <div className="h-full bg-white dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm p-6 relative overflow-hidden">
                            <div className="flex flex-col sm:flex-row gap-5 items-start">
                                <div className="relative shrink-0">
                                    <div className="w-24 h-24 rounded-full bg-gray-200 dark:bg-white/10" />
                                </div>
                                <div className="flex-1 min-w-0 pt-1 space-y-3">
                                    <div className="h-8 w-48 bg-gray-200 dark:bg-white/10 rounded-md" />
                                    <div className="h-5 w-32 bg-gray-200 dark:bg-white/10 rounded-md" />
                                    <div className="flex gap-2">
                                        <div className="h-6 w-20 bg-gray-200 dark:bg-white/10 rounded-full" />
                                        <div className="h-6 w-24 bg-gray-200 dark:bg-white/10 rounded-full" />
                                    </div>
                                </div>
                            </div>
                            <div className="mt-6 space-y-2">
                                <div className="h-4 w-full bg-gray-200 dark:bg-white/10 rounded-md" />
                                <div className="h-4 w-3/4 bg-gray-200 dark:bg-white/10 rounded-md" />
                            </div>
                        </div>
                    </div>
                </div>

                {/* 2. Tabs Skeleton */}
                <div className="w-full">
                    <div className="flex items-center justify-between sticky top-0 -mx-6 px-6 md:-mx-10 md:px-10 py-4 z-40 bg-white dark:bg-black">
                        <div className="bg-white/50 dark:bg-zinc-900/50 border border-gray-200 dark:border-gray-800 p-1 rounded-xl flex gap-1">
                            {[1, 2, 3, 4].map((_, i) => (
                                <div key={i} className="h-10 w-24 bg-gray-200 dark:bg-white/10 rounded-lg" />
                            ))}
                        </div>
                    </div>

                    {/* Metrics Grid Skeleton */}
                    <div className="h-full bg-white dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/10 shadow-sm p-6 mt-8">
                        <div className="flex items-center justify-between mb-6">
                            <div className="h-6 w-48 bg-gray-200 dark:bg-white/10 rounded-md" />
                            <div className="h-6 w-16 bg-gray-200 dark:bg-white/10 rounded-md" />
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                            {[...Array(6)].map((_, i) => (
                                <div key={i} className="p-4 rounded-xl bg-gray-50/50 dark:bg-white/5 border border-gray-100 dark:border-white/5 space-y-3">
                                    <div className="flex justify-between">
                                        <div className="w-8 h-8 rounded-lg bg-gray-200 dark:bg-white/10" />
                                    </div>
                                    <div className="space-y-1">
                                        <div className="h-8 w-24 bg-gray-200 dark:bg-white/10 rounded-md" />
                                        <div className="h-4 w-16 bg-gray-200 dark:bg-white/10 rounded-md" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="space-y-8"
        >
            {/* 1. Top Section: Profile & Quick Stats Key Info */}
            <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
                {/* Creator Profile Card - Full Width */}
                <div className="md:col-span-5 space-y-6">
                    <CreatorProfileCard
                        profileImage={profileImage as string | null | undefined}
                        name={String(activeCreator.name ?? activeCreator.NAME ?? "Unknown")}
                        username={String(derivedUsername ?? "unknown")}
                        niche={String(activeCreator.niche ?? activeCreator.NICHE ?? activeCreator.category_name ?? "") || null}
                        location={influencerLocation}
                        biography={(activeCreator.biography ?? activeCreator.biology) as string | null | undefined}
                        profileLink={activeCreator.profile_link as string | null | undefined}
                        externalUrl={activeCreator.external_url as string | string[] | null | undefined}
                        isVerified={isVerified}
                        onDownloadPdf={onDownloadPdf}
                        pdfLoading={pdfLoading}
                    />
                </div>
            </div>

            {/* 2. Tabs for Deep Dive */}
            <Tabs defaultValue="overview" className="w-full">
                <div className="flex items-center justify-between z-40 bg-white dark:bg-black sticky top-0 -mx-6 px-6 md:-mx-10 md:px-10 py-4">
                    <TabsList className="bg-white/50 dark:bg-zinc-900/50 backdrop-blur-sm border border-gray-200 dark:border-gray-800 p-1 rounded-xl h-auto flex w-full overflow-x-auto hide-scrollbar shadow-sm justify-start sm:justify-center sm:w-auto sm:inline-flex">
                        <TabsTrigger
                            value="overview"
                            className="rounded-lg px-6 py-3 data-[state=active]:bg-white dark:data-[state=active]:bg-zinc-800 data-[state=active]:text-purple-600 dark:data-[state=active]:text-purple-400 data-[state=active]:shadow-sm transition-all"
                        >
                            Overview
                        </TabsTrigger>
                        <TabsTrigger
                            value="metrics"
                            className="rounded-lg px-6 py-3 data-[state=active]:bg-white dark:data-[state=active]:bg-zinc-800 data-[state=active]:text-purple-600 dark:data-[state=active]:text-purple-400 data-[state=active]:shadow-sm transition-all"
                        >
                            Analysis & Metrics
                        </TabsTrigger>
                        <TabsTrigger
                            value="ai-insight"
                            className="rounded-lg px-6 py-3 data-[state=active]:bg-white dark:data-[state=active]:bg-zinc-800 data-[state=active]:text-purple-600 dark:data-[state=active]:text-purple-400 data-[state=active]:shadow-sm transition-all"
                        >
                            AI Insight
                        </TabsTrigger>
                        <TabsTrigger
                            value="post-analysis"
                            className="rounded-lg px-6 py-3 data-[state=active]:bg-white dark:data-[state=active]:bg-zinc-800 data-[state=active]:text-purple-600 dark:data-[state=active]:text-purple-400 data-[state=active]:shadow-sm transition-all"
                        >
                            Post Analysis
                        </TabsTrigger>
                    </TabsList>
                </div>

                {/* Overview Tab */}
                <TabsContent value="overview" className="space-y-8 mt-0 animate-in fade-in-5 slide-in-from-bottom-2 duration-300">
                    {/* Key Metrics Grid */}
                    <InfluencerInfoCard
                        followers={profileFollowers}
                        following={profileFollowing}
                        engagementRate={profileEngagementRate}
                        realFollowersPct={realFollowersPct}
                        suspiciousFollowers={suspiciousFollowers}
                        avgLikes={profileAvgLikes}
                        avgComments={profileAvgComments}
                        posts={postsCount}
                    />
                </TabsContent>
                {/* Detailed Charts */}
                <TabsContent value="metrics" className="space-y-8 mt-0 animate-in fade-in-5 slide-in-from-bottom-2 duration-300">
                    <IndustryStandardComparison
                        anchor={activeCreator}
                        peers={allResults.filter((r: Record<string, unknown>) => r.industry_standard === true)}
                        isLoadingMore={isPolling}
                        comparisonMode="profession"
                    />

                    <DashboardMetrics
                        metrics={metrics || {}} // Assuming normalizedMetrics is equivalent to existing metrics
                        influencer={activeCreator}
                        anchor={activeCreator} // Assuming anchorCreator is activeCreator
                        peers={allResults.filter((r: Record<string, unknown>) => r.industry_standard === true)} // Assuming peers is the same as for IndustryStandardComparison
                        isLoading={isLoading}
                    />
                </TabsContent>
                {/* AI Insight */}
                <TabsContent value="ai-insight" className="space-y-8 mt-0 animate-in fade-in-5 slide-in-from-bottom-2 duration-300">
                    <AIInsight influencerData={activeCreator} />
                </TabsContent>
                {/* Post Analysis */}
                <TabsContent value="post-analysis" className="space-y-6 mt-0 animate-in fade-in-5 slide-in-from-bottom-2 duration-300">
                    {/* Last 5 Posts Analysis */}
                    <PostAnalysisCard
                        posts={((activeCreator.recentContent ?? activeCreator.posts) ?? []) as Parameters<typeof PostAnalysisCard>[0]["posts"]}
                        isLoading={isLoading}
                    />
                </TabsContent>
            </Tabs>
        </motion.div>
    )
}

export default ProfileSidebarContent
