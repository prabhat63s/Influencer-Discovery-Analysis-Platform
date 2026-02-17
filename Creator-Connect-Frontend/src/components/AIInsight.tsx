"use client"

import React, { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Sparkles, Target, RefreshCw, AlertCircle, BarChart3, CheckCircle, AlertTriangle } from 'lucide-react'
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"

interface Post {
    caption?: string;
    text?: string;
    like_count?: number;
    likes?: number;
    comment_count?: number;
    comments?: number;
    timestamp?: string;
    date?: string;
    [key: string]: unknown;
}

interface AIInsightProps {
    influencerData: Record<string, unknown> | null
}

// Extract hashtags helper
const extractHashtags = (text: string) => {
    if (!text) return [];
    const matches = text.match(/#[a-zA-Z0-9_]+/g);
    return matches || [];
};

const AIInsight: React.FC<AIInsightProps> = ({ influencerData }) => {
    const [insight, setInsight] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const generateInsight = React.useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/ai-insight`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(influencerData)
            });

            if (!response.ok) throw new Error('Failed to generate insight');
            const data = await response.json();
            setInsight(data.insight);
        } catch (err) {
            console.error(err);
            setError("AI analysis unavailable at the moment.");
        } finally {
            setLoading(false);
        }
    }, [influencerData]);

    useEffect(() => {
        if (influencerData?.id) {
            generateInsight();
        }
    }, [influencerData?.id, generateInsight]);

    // Parse sections from the text, handling both markdown headers and emoji headers
    const sections = insight
        ? insight.split(/(?=###|📊|✅|⚠️|🎯|Performance Highlights:|Key Strengths:|Considerations:|Recommendation:)/g)
            .filter((s) => s.trim().length > 0)
            .map(s => s.trim())
        : [];

    // Map keywords to styling
    const getStyleForSection = (title: string) => {
        const t = title.toLowerCase();

        // Performance Highlights (Purple/Pink like screenshot)
        if (t.includes('performance') || t.includes('highlights') || t.includes('📊')) {
            return {
                icon: <BarChart3 className="w-5 h-5 text-purple-400" />, // Using BarChart3 for graph look
                bg: "bg-[#2D1B36] border-purple-500/20", // Dark purple bg
                badge: "bg-purple-500/20 text-purple-300",
                title: "text-purple-300"
            };
        }

        // Key Strengths (Green)
        if (t.includes('strength') || t.includes('positive') || t.includes('✅')) {
            return {
                icon: <CheckCircle className="w-5 h-5 text-green-400" />,
                bg: "bg-[#16291E] border-green-500/20", // Dark green bg
                badge: "bg-green-500/20 text-green-300",
                title: "text-green-300"
            };
        }

        // Considerations (Orange/Amber)
        if (t.includes('consideration') || t.includes('improvement') || t.includes('weakness') || t.includes('⚠️')) {
            return {
                icon: <AlertTriangle className="w-5 h-5 text-amber-400" />,
                bg: "bg-[#2F2215] border-amber-500/20", // Dark amber bg
                badge: "bg-amber-500/20 text-amber-300",
                title: "text-amber-300"
            };
        }

        // Recommendation (Deep Purple/Red)
        if (t.includes('recommendation') || t.includes('target') || t.includes('🎯')) {
            return {
                icon: <Target className="w-5 h-5 text-pink-400" />,
                bg: "bg-[#2D1522] border-pink-500/20", // Dark pink/red bg
                badge: "bg-pink-500/20 text-pink-300",
                title: "text-pink-300"
            };
        }

        // Default
        return {
            icon: <Sparkles className="w-5 h-5 text-gray-400" />,
            bg: "bg-gray-50/50 dark:bg-white/5 border-gray-200 dark:border-white/10",
            badge: "bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300",
            title: "text-gray-900 dark:text-white"
        };
    }

    return (
        <div className="space-y-6">
            {/* Header Section */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-linear-to-br from-purple-500 to-indigo-600 rounded-xl shadow-lg shadow-purple-500/20">
                        <Sparkles className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h3 className="font-bold text-xl text-gray-900 dark:text-white">AI Analysis</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Deep content & performance review</p>
                    </div>
                </div>
                {insight && !loading && (
                    <Button variant="outline" size="sm" onClick={generateInsight} className="text-xs h-9 gap-2">
                        <RefreshCw className="w-3.5 h-3.5" /> Regenerate
                    </Button>
                )}
            </div>

            {loading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {[1, 2, 3, 4].map((i) => (
                        <div key={i} className="p-5 rounded-2xl border bg-gray-50/50 dark:bg-white/5 border-gray-200 dark:border-white/10 space-y-3">
                            <div className="flex items-center gap-2">
                                <Skeleton className="h-8 w-8 rounded-lg" />
                                <Skeleton className="h-6 w-32 rounded-md" />
                            </div>
                            <div className="space-y-2">
                                <Skeleton className="h-4 w-full" />
                                <Skeleton className="h-4 w-[90%]" />
                                <Skeleton className="h-4 w-[95%]" />
                            </div>
                        </div>
                    ))}
                </div>
            ) : error ? (
                <div className="flex items-center gap-3 p-4 text-sm text-red-600 bg-red-50 dark:bg-red-900/10 rounded-xl border border-red-100 dark:border-red-900/20">
                    <AlertCircle className="w-5 h-5 shrink-0" />
                    {error}
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
                    {sections.map((section, idx) => {
                        const [titleLine, ...content] = section.split('\n');
                        const body = content.join('\n').trim();
                        if (!body) return null;
                        const style = getStyleForSection(titleLine);

                        return (
                            <motion.div
                                key={idx}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: idx * 0.1 }}
                                className={`p-5 rounded-2xl border ${style.bg} transition-all hover:shadow-md flex flex-col`}
                            >
                                <div className={`self-start inline-flex items-center gap-2 px-3 py-1 rounded-lg mb-3 ${style.badge}`}>
                                    {style.icon}
                                    <span className="font-bold text-sm tracking-tight">{titleLine.replace(/^[#\s📊✅⚠️🎯]+|[:]+$/g, '').trim()}</span>
                                </div>

                                <div className="text-sm leading-relaxed text-gray-700 dark:text-gray-300/90 pl-1">
                                    {body.split('\n').map((line, i) => (
                                        <div key={i} className="flex gap-2 mb-1.5 last:mb-0">
                                            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-current opacity-50 shrink-0" />
                                            <span>{line.replace(/^[-*•]\s*/, '').trim()}</span>
                                        </div>
                                    ))}
                                </div>
                            </motion.div>
                        )
                    })}
                </div>
            )}

            {/* Post Analysis Cards - Modern Grid */}
            {hasPostData(influencerData) && influencerData && (
                <div className="pt-6 border-t border-gray-100 dark:border-white/10">
                    <h3 className="font-bold text-lg mb-6 flex items-center gap-2">
                        <span className="w-1 h-6 bg-purple-500 rounded-full"></span>
                        Recent Content Performance
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {((influencerData.detailed_post_analysis as Record<string, unknown>[]) || (influencerData.recent_posts as Record<string, unknown>[]) || []).slice(0, 4).map((post: Record<string, unknown>, i: number) => {
                            const caption = String(post.caption ?? post.text ?? "");
                            const hashtags = extractHashtags(caption);
                            const cleanCaption = caption.replace(/#[a-zA-Z0-9_]+/g, '').trim().substring(0, 100) + '...';

                            return (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, y: 10 }}
                                    whileInView={{ opacity: 1, y: 0 }}
                                    viewport={{ once: true }}
                                    transition={{ delay: i * 0.1 }}
                                    className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 p-4 rounded-xl hover:shadow-md transition-shadow group"
                                >
                                    <div className="flex justify-between items-start mb-3">
                                        <div className="flex gap-2">
                                            <Badge variant="outline" className="bg-pink-50 text-pink-700 border-pink-100 dark:bg-pink-500/10 dark:text-pink-300 dark:border-pink-500/20 group-hover:bg-pink-100 dark:group-hover:bg-pink-500/20 transition-colors">
                                                ❤️ {Number(post.like_count ?? post.likes ?? 0)}
                                            </Badge>
                                            <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-100 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20 group-hover:bg-blue-100 dark:group-hover:bg-blue-500/20 transition-colors">
                                                💬 {Number(post.comment_count ?? post.comments ?? 0)}
                                            </Badge>
                                        </div>
                                        <span className="text-xs text-muted-foreground">{new Date(Number(post.timestamp) || Number(post.date) || Date.now()).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                                    </div>
                                    <p className="text-xs text-gray-600 dark:text-gray-300 mb-3 leading-relaxed line-clamp-2">
                                        {cleanCaption || "No caption provided"}
                                    </p>
                                    <div className="flex flex-wrap gap-1">
                                        {hashtags.slice(0, 2).map((tag: string, t: number) => (
                                            <span key={t} className="text-[10px] bg-gray-100 dark:bg-zinc-800 text-gray-500 px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-700">
                                                {tag}
                                            </span>
                                        ))}
                                    </div>
                                </motion.div>
                            )
                        })}
                    </div>
                </div>
            )}
        </div>
    )
}

function hasPostData(data: Record<string, unknown> | null): boolean {
    if (!data) return false;
    return (Array.isArray(data.detailed_post_analysis) && data.detailed_post_analysis.length > 0) ||
        (Array.isArray(data.recent_posts) && data.recent_posts.length > 0);
}

export default AIInsight
