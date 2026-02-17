"use client"

import { motion, Variants } from "framer-motion"
import type { CreatorProfile } from "@/types/creator.types"
import { CheckCircle, Heart, MessageCircle } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"

const MOCK_CREATORS = [
    {
        name: "Khabane lame",
        handle: "khaby.lame",
        avatar: "https://i.pravatar.cc/150?u=khaby",
        niche: "Entertainment",
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
        name: "MrBeast",
        handle: "mrbeast",
        avatar: "https://i.pravatar.cc/150?u=mrbeast",
        niche: "Entertainment",
        verified: true,
        stats: { followers: "124.4M", engagement: "7.34%", posts: "1.1k" },
        collabs: [
            "https://i.pravatar.cc/150?u=collab4",
            "https://i.pravatar.cc/150?u=collab5",
        ],
        recentContent: [
            { url: "https://images.unsplash.com/photo-1628155930542-3c7a64e2c833?w=400&h=400&fit=crop", likes: "3.4M", comments: "45k" },
            { url: "https://images.unsplash.com/photo-1598550476439-6847785fcea6?w=400&h=400&fit=crop", likes: "2.8M", comments: "32k" },
            { url: "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=400&h=400&fit=crop", likes: "4.1M", comments: "51k" },
            { url: "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=400&h=400&fit=crop", likes: "1.9M", comments: "28k" }
        ]
    },
    {
        name: "Elena Rodriguez",
        handle: "elena_travels",
        avatar: "https://i.pravatar.cc/150?u=elena",
        niche: "Travel",
        verified: false,
        stats: { followers: "420k", engagement: "7.1%", posts: "890" },
        collabs: [
            "https://i.pravatar.cc/150?u=collab6",
            "https://i.pravatar.cc/150?u=collab7",
            "https://i.pravatar.cc/150?u=collab8",
            "https://i.pravatar.cc/150?u=collab9",
        ],
        recentContent: [
            { url: "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=400&h=400&fit=crop", likes: "45k", comments: "1.2k" },
            { url: "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=400&h=400&fit=crop", likes: "38k", comments: "950" },
            { url: "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=400&h=400&fit=crop", likes: "52k", comments: "1.5k" },
            { url: "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=400&h=400&fit=crop", likes: "29k", comments: "820" }
        ]
    }
];


interface ProfileCardProps {
    onViewProfile: (creator: CreatorProfile) => void;
}

const ProfileCard = ({ onViewProfile }: ProfileCardProps) => {
    const containerVariants: Variants = {
        hidden: { opacity: 0 },
        visible: {
            opacity: 1,
            transition: {
                staggerChildren: 0.1
            }
        }
    };

    const itemVariants: Variants = {
        hidden: { y: 20, opacity: 0 },
        visible: {
            y: 0,
            opacity: 1,
            transition: {
                type: "spring",
                stiffness: 100
            }
        }
    };

    return (
        <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="flex flex-col gap-8 w-full"
        >
            {MOCK_CREATORS.map((creator) => (
                <motion.div
                    key={creator.handle}
                    variants={itemVariants}
                    className="bg-card w-full rounded-xl overflow-hidden"
                >
                    {/* Header Section */}
                    <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">

                        {/* Profile Info */}
                        <div className="flex items-center gap-4 min-w-[200px]">
                            <Avatar className="w-16 h-16 border-2 border-background shadow-md">
                                <AvatarImage src={creator.avatar} />
                                <AvatarFallback>{creator.name[0]}</AvatarFallback>
                            </Avatar>
                            <div>
                                <div className="flex items-center gap-1.5">
                                    <h3 className="font-bold text-lg">{creator.name}</h3>
                                    {creator.verified && <CheckCircle className="w-4 h-4 fill-blue-500 text-white" />}
                                </div>
                                <p className="text-muted-foreground text-sm">@{creator.handle}</p>
                            </div>
                        </div>

                        {/* Stats */}
                        <div className="flex items-center gap-12 flex-1 pl-8">
                            <div>
                                <p className="font-bold text-lg">{creator.stats.followers}</p>
                                <p className="text-xs text-muted-foreground font-medium">Followers</p>
                            </div>
                            <div>
                                <p className="font-bold text-lg">{creator.stats.engagement}</p>
                                <p className="text-xs text-muted-foreground font-medium">Engagement rate</p>
                            </div>
                            <div>
                                <p className="font-bold text-lg">India</p>
                                <p className="text-xs text-muted-foreground font-medium">Location</p>
                            </div>
                            <div>
                                <p className="font-bold text-lg">Gaming</p>
                                <p className="text-xs text-muted-foreground font-medium">Niche</p>
                            </div>
                        </div>
                        <Button
                            variant="outline"
                            className="font-semibold rounded-full px-6"
                            onClick={() => onViewProfile(creator)}
                        >
                            View profile
                        </Button>
                    </div>

                    {/* Content Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                        {creator.recentContent.map((content, idx) => (
                            <div key={idx} className="aspect-3/3 rounded-lg overflow-hidden relative group cursor-pointer bg-muted">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                    src={content.url}
                                    alt={`Post ${idx + 1}`}
                                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                                />
                                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-4 text-white font-bold">
                                    <div className="flex items-center gap-1.5">
                                        <Heart className="w-4 h-4 fill-white" />
                                        <span className="text-sm shadow-sm">{content.likes}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <MessageCircle className="w-4 h-4 fill-white" />
                                        <span className="text-sm shadow-sm">{content.comments}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </motion.div>
            ))}
        </motion.div>
    )
}

export default ProfileCard