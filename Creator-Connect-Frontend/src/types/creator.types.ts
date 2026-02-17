export type CreatorContent = {
    url: string;
    likes: string;
    comments: string;
};

export type CreatorStats = {
    followers: string;
    engagement: string;
    posts: string;
};

export type CreatorProfile = {
    id?: string;
    name: string;
    handle: string;
    avatar?: string;
    niche: string;
    location?: string;
    verified: boolean;
    stats?: CreatorStats;
    recentContent?: CreatorContent[];
    collabs?: string[];

    // Raw API fields (optional)
    Id?: string;
    profile_pic_url?: string;
    followers?: number | string;
    engagement_rate?: number | string;
    posts_count?: number | string;
    posts?: Record<string, unknown>[];
    metrics?: Record<string, unknown>;
    is_verified?: boolean;
    NAME?: string;
    NICHE?: string;
    LOCATION?: string;
    PROFILE_LINK?: string;
    username?: string;
    PROFILE_PIC_URL?: string;
    [key: string]: unknown;
};

export interface ProfileCardProps {
    onViewProfile: (creator: CreatorProfile) => void;
    creators?: CreatorProfile[];
    databaseResults?: CreatorProfile[];
}
