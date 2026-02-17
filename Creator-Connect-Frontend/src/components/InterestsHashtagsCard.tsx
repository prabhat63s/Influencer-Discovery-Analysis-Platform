"use client"

import React from 'react'
import { motion } from 'framer-motion'
import { Hash, Tag } from 'lucide-react'
import { Badge } from "@/components/ui/badge"

interface InterestsHashtagsCardProps {
    lifestyleInterests: string | string[] | null
    postHashtags: string | string[] | null
}

const InterestsHashtagsCard: React.FC<InterestsHashtagsCardProps> = ({ lifestyleInterests, postHashtags }) => {

    // Helper to parse lists
    const parseList = (input: string | string[] | null) => {
        if (!input) return [];
        if (Array.isArray(input)) return input;

        if (typeof input === 'string') {
            if (input.toLowerCase() === 'n/a') return [];
            try {
                // Try JSON first
                const parsed = JSON.parse(input);
                if (Array.isArray(parsed)) return parsed;
            } catch { }

            // Split by common delimiters
            return input.split(/,|;|\n/).map(s => s.trim()).filter(s => s.length > 0);
        }

        return [];
    };

    const interests = parseList(lifestyleInterests);
    const hashtags = parseList(postHashtags);

    if (interests.length === 0 && hashtags.length === 0) return null;

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Interests Column */}
            <motion.div
                initial={{ opacity: 0, x: -10 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl p-6 shadow-sm"
            >
                <div className="flex items-center gap-2 mb-6">
                    <div className="p-2 bg-indigo-50 dark:bg-indigo-500/10 rounded-lg text-indigo-600 dark:text-indigo-400">
                        <Tag size={18} />
                    </div>
                    <h3 className="font-semibold text-gray-900 dark:text-white">Top Interests</h3>
                </div>

                {interests.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                        {interests.map((interest, i) => (
                            <Badge
                                key={i}
                                variant="secondary"
                                className="px-3 py-1.5 text-sm bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20 border-transparent transition-colors"
                            >
                                {interest}
                            </Badge>
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-8 text-muted-foreground bg-gray-50 dark:bg-white/5 rounded-xl border border-dashed border-gray-200 dark:border-white/10">
                        <span className="text-sm">No interest types available</span>
                    </div>
                )}
            </motion.div>

            {/* Hashtags Column */}
            <motion.div
                initial={{ opacity: 0, x: 10 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.1 }}
                className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl p-6 shadow-sm"
            >
                <div className="flex items-center gap-2 mb-6">
                    <div className="p-2 bg-pink-50 dark:bg-pink-500/10 rounded-lg text-pink-600 dark:text-pink-400">
                        <Hash size={18} />
                    </div>
                    <h3 className="font-semibold text-gray-900 dark:text-white">Popular Hashtags</h3>
                </div>

                {hashtags.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                        {hashtags.map((tag, i) => (
                            <a
                                key={i}
                                href={`https://www.instagram.com/explore/tags/${tag.replace('#', '')}`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-3 py-1.5 text-sm rounded-full bg-pink-50 text-pink-700 hover:bg-pink-100 dark:bg-pink-500/10 dark:text-pink-300 dark:hover:bg-pink-500/20 border border-transparent hover:border-pink-200 transition-all cursor-pointer"
                            >
                                <span className="opacity-50 mr-0.5">#</span>{tag.replace('#', '')}
                            </a>
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-8 text-muted-foreground bg-gray-50 dark:bg-white/5 rounded-xl border border-dashed border-gray-200 dark:border-white/10">
                        <span className="text-sm">No hashtag data available</span>
                    </div>
                )}
            </motion.div>
        </div>
    )
}

export default InterestsHashtagsCard
