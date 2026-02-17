
import React, { useState } from 'react'
import { Heart, MessageCircle, BarChart2, ExternalLink, Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'

import { Skeleton } from "@/components/ui/skeleton"

interface Post {
    image_url?: string;
    url?: string;
    display_url?: string;
    thumbnail_url?: string;
    likes?: string | number;
    comments?: string | number;
    caption?: string;
    engagement?: string;
    permalink?: string;
    id?: string;
}

interface PostAnalysisCardProps {
    posts: Post[];
    isLoading?: boolean;
}

const PostAnalysisCard = ({ posts, isLoading }: PostAnalysisCardProps) => {
    if (isLoading) {
        return (
            <div className="space-y-6">
                <div className="flex items-center gap-2 pb-2 border-b border-border">
                    <BarChart2 className="w-5 h-5 text-primary" />
                    <h3 className="font-semibold text-lg">Last 5 Posts Analysis</h3>
                </div>
                <div className="space-y-4">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="rounded-xl border border-border bg-card shadow-sm overflow-hidden p-4 flex gap-4">
                            <Skeleton className="w-20 h-20 sm:w-32 sm:h-32 rounded-lg shrink-0" />
                            <div className="flex-1 space-y-3">
                                <div className="flex justify-between">
                                    <div className="flex gap-3">
                                        <Skeleton className="w-16 h-8 rounded-md" />
                                        <Skeleton className="w-16 h-8 rounded-md" />
                                    </div>
                                    <Skeleton className="w-20 h-6 rounded-md" />
                                </div>
                                <Skeleton className="w-full h-4 rounded-md" />
                                <Skeleton className="w-3/4 h-4 rounded-md" />
                                <Skeleton className="w-full h-12 rounded-lg mt-2" />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    if (!posts || posts.length === 0) return null;

    // Calculate average metrics for the displayed posts to generate relative insights
    const avgLikes = posts.reduce((acc, p) => acc + (Number(p.likes) || 0), 0) / (posts.length || 1);
    const avgComments = posts.reduce((acc, p) => acc + (Number(p.comments) || 0), 0) / (posts.length || 1);

    const getInsight = (post: Post) => {
        const likes = Number(post.likes) || 0;
        const comments = Number(post.comments) || 0;

        if (likes > avgLikes * 1.5) return <span><span className="font-bold text-green-600 dark:text-green-400">High Performance:</span> {((likes / avgLikes) * 100 - 100).toFixed(0)}% more likes than recent average.</span>;
        if (comments > avgComments * 2) return <span><span className="font-bold text-blue-600 dark:text-blue-400">Sparking Conversation:</span> {((comments / avgComments) * 100 - 100).toFixed(0)}% more comments than usual.</span>;
        if (likes < avgLikes * 0.5) return <span><span className="font-bold text-orange-600 dark:text-orange-400">Growth Opportunity:</span> Engagement is lower than your recent trend.</span>;
        return <span><span className="font-bold text-purple-700 dark:text-purple-400">Consistent Performance:</span> Engagement aligns with recent content.</span>;
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-2 pb-2 border-b border-border">
                <BarChart2 className="w-5 h-5 text-primary" />
                <h3 className="font-semibold text-lg">Last 5 Posts Analysis</h3>
            </div>

            <div className="space-y-4">
                {posts.map((post, index) => (
                    <PostCardItem
                        key={post.id || index}
                        post={post}
                        index={index}
                        insight={getInsight(post)}
                    />
                ))}
            </div>
        </div>
    )
}

const PostCardItem = ({ post, index, insight }: { post: Post; index: number; insight: React.ReactNode }) => {
    const [imageError, setImageError] = useState(false);

    // Helper to check if a URL is likely a valid image source
    const isValidImage = (url: string | undefined): boolean => {
        if (!url) return false;
        if (url.includes('instagram.com/p/') || url.includes('instagram.com/reel/')) return false;
        return true;
    };

    const getPostImage = (post: Post): string | null => {
        if (isValidImage(post.image_url)) return post.image_url!;
        if (isValidImage(post.thumbnail_url)) return post.thumbnail_url!;
        if (isValidImage(post.display_url)) return post.display_url!;
        if (isValidImage(post.url)) return post.url!;
        return null;
    };

    const getProxyUrl = (url?: string) => {
        if (!url) return "";
        if (url.startsWith("data:")) return url;
        if (url.startsWith("http")) {
            if (url.includes("/api/proxy/image")) return url;
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
            return `${apiUrl}/api/proxy/image?url=${encodeURIComponent(url)}`;
        }
        return url;
    };

    const formatMetric = (val: string | number | undefined) => {
        if (val === undefined || val === null) return "0";
        if (typeof val === 'string') return val;
        return new Intl.NumberFormat('en-US', { notation: "compact", compactDisplay: "short" }).format(val);
    };

    const rawImageUrl = getPostImage(post);
    const imageUrl = rawImageUrl ? getProxyUrl(rawImageUrl) : null;
    const permalink = post.permalink || (post.url?.includes('instagram.com') ? post.url : undefined);

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className="rounded-xl border border-border bg-card shadow-sm overflow-hidden"
        >
            <div className="p-4 flex flex-col sm:flex-row gap-4">
                <div className="relative w-full sm:w-32 aspect-square shrink-0 rounded-lg overflow-hidden bg-muted flex flex-col items-center justify-center">
                    {imageUrl && !imageError ? (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                            src={imageUrl}
                            alt={`Post ${index + 1}`}
                            className="object-cover w-full h-full hover:scale-105 transition-transform duration-500"
                            referrerPolicy="no-referrer"
                            onError={() => setImageError(true)}
                            loading="lazy"
                        />
                    ) : (
                        <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-2 text-center gap-2 bg-secondary/30">
                            <ExternalLink className="w-6 h-6 opacity-30" />
                            <span className="text-[10px] uppercase font-bold opacity-50">No Preview</span>
                        </div>
                    )}
                </div>

                <div className="flex-1 min-w-0 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                        <div className="flex gap-3">
                            <div className="flex items-center gap-1.5 text-pink-600 dark:text-pink-400 bg-pink-50 dark:bg-pink-950/20 px-2 py-1 rounded-md border border-pink-100 dark:border-pink-900/30">
                                <Heart className="w-3.5 h-3.5" />
                                <span className="text-sm font-bold">{formatMetric(post.likes)}</span>
                            </div>
                            <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/20 px-2 py-1 rounded-md border border-blue-100 dark:border-blue-900/30">
                                <MessageCircle className="w-3.5 h-3.5" />
                                <span className="text-sm font-bold">{formatMetric(post.comments)}</span>
                            </div>
                        </div>
                        {permalink && (
                            <a
                                href={permalink}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs flex items-center gap-1 text-muted-foreground hover:text-primary transition-colors border border-border px-2 py-1 rounded-md"
                            >
                                View Post <ExternalLink className="w-3 h-3" />
                            </a>
                        )}
                    </div>

                    {post.caption && (
                        <p className="text-sm text-foreground/80 line-clamp-2 italic">
                            &quot;{post.caption}&quot;
                        </p>
                    )}

                    <div className="flex-col text-xs text-purple-900/80 dark:text-purple-200 bg-purple-50 dark:bg-purple-950/20 p-2.5 rounded-lg border border-purple-100 dark:border-purple-900/30 leading-relaxed flex gap-1 items-start">
                        <div className='flex items-center gap-1'>
                            <Sparkles className="w-3 h-3 text-purple-500 mt-0.5 shrink-0" />
                            <span className="font-bold uppercase text-[10px] text-purple-700 dark:text-purple-400 mr-1 tracking-wide">AI INSIGHT</span>
                        </div>
                        {insight}
                    </div>
                </div>
            </div>
        </motion.div>
    );
};

export default PostAnalysisCard
