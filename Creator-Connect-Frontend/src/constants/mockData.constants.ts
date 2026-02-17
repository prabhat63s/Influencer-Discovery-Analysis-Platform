import { CreatorProfile } from "@/types/creator.types";

export const MOCK_CREATORS: CreatorProfile[] = [
    {
        name: "Khabane lame",
        handle: "khaby.lame",
        avatar: "https://i.pravatar.cc/150?u=khaby",
        niche: "Entertainment",
        location: "Italy",
        verified: true,
        stats: { followers: "160.4M", engagement: "6.33%", posts: "2.4k" },
        collabs: [
            "https://i.pravatar.cc/150?u=collab1",
            "https://i.pravatar.cc/150?u=collab2",
            "https://i.pravatar.cc/150?u=collab3",
        ],
        recentContent: [
            { url: "https://images.unsplash.com/photo-1590523277543-a94d2e4eb00b?w=400&h=400&fit=crop", likes: "1.2M", comments: "12k" },
            { url: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop", likes: "850k", comments: "8.5k" },
            { url: "https://images.unsplash.com/photo-1520697830682-bbb6e85e2b0b?w=400&h=400&fit=crop", likes: "2.1M", comments: "21k" },
            { url: "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=400&h=400&fit=crop", likes: "1.5M", comments: "15k" }
        ]
    },
    {
        name: "Marques Brownlee",
        handle: "mkbhd",
        avatar: "https://i.pravatar.cc/150?u=mkbhd",
        niche: "Tech",
        location: "USA",
        verified: true,
        stats: { followers: "4.8M", engagement: "4.2%", posts: "1.8k" },
        collabs: ["https://i.pravatar.cc/150?u=tech1", "https://i.pravatar.cc/150?u=tech2"],
        recentContent: [
            { url: "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&h=400&fit=crop", likes: "240k", comments: "3.2k" },
            { url: "https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=400&h=400&fit=crop", likes: "190k", comments: "2.1k" },
            { url: "https://images.unsplash.com/photo-1468436139062-f60a71c5c892?w=400&h=400&fit=crop", likes: "310k", comments: "4.5k" },
            { url: "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop", likes: "150k", comments: "1.8k" }
        ]
    },
    {
        name: "Matilda Djerf",
        handle: "matildadjerf",
        avatar: "https://i.pravatar.cc/150?u=matilda",
        niche: "Fashion",
        location: "Sweden",
        verified: true,
        stats: { followers: "3.1M", engagement: "8.15%", posts: "4.2k" },
        collabs: ["https://i.pravatar.cc/150?u=fash1"],
        recentContent: [
            { url: "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=400&h=400&fit=crop", likes: "310k", comments: "1.1k" },
            { url: "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=400&h=400&fit=crop", likes: "280k", comments: "1.9k" },
            { url: "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop", likes: "350k", comments: "3.1k" },
            { url: "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=400&h=400&fit=crop", likes: "310k", comments: "1.1k" }
        ]
    },
    {
        name: "Joshua Weissman",
        handle: "joshuaweissman",
        avatar: "https://i.pravatar.cc/150?u=joshua",
        niche: "Food",
        location: "USA",
        verified: true,
        stats: { followers: "1.5M", engagement: "5.4%", posts: "980" },
        collabs: ["https://i.pravatar.cc/150?u=food1", "https://i.pravatar.cc/150?u=food2"],
        recentContent: [
            { url: "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=400&h=400&fit=crop", likes: "95k", comments: "1.2k" },
            { url: "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&h=400&fit=crop", likes: "150k", comments: "2.1k" },
            { url: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=400&h=400&fit=crop", likes: "85k", comments: "1.1k" },
            { url: "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=400&h=400&fit=crop", likes: "95k", comments: "1.2k" }
        ]
    }
];
