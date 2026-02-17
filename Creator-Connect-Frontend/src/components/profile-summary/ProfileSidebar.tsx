"use client"

import React from 'react'
import { motion, Variants } from "framer-motion"
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetDescription,
} from "@/components/ui/sheet"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MapPin, Calendar, CheckCircle, Mail, Instagram, Twitter, BarChart3, Globe } from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent } from "@/components/ui/card"

interface ProfileSidebarProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
    creator: Record<string, unknown> | null
}

const ProfileSidebar = ({ isOpen, onOpenChange, creator }: ProfileSidebarProps) => {
    if (!creator) return null

    const containerVariants: Variants = {
        hidden: { opacity: 0, x: 20 },
        visible: {
            opacity: 1,
            x: 0,
            transition: { duration: 0.4, ease: "easeOut" }
        }
    }

    return (
        <Sheet open={isOpen} onOpenChange={onOpenChange}>
            <SheetContent className="w-full sm:max-w-[60%] sm:w-[60%] p-0 overflow-y-auto overflow-x-hidden bg-background">
                <SheetHeader>
                    <SheetTitle>Creator Profile: {String(creator.name ?? "")}</SheetTitle>
                    <SheetDescription>View details, stats, and content for {String(creator.name ?? "")}</SheetDescription>
                </SheetHeader>
                <motion.div
                    initial="hidden"
                    animate="visible"
                    variants={containerVariants}
                >
                    {/* Banner */}
                    <div className="h-48 bg-linear-to-r from-blue-600 to-purple-600 relative w-full">
                        <Button
                            variant="secondary"
                            size="icon"
                            className="absolute top-4 right-14 bg-white/20 hover:bg-white/40 text-white border-0"
                        >
                            <Globe className="w-4 h-4" />
                        </Button>
                    </div>

                    <div className="px-8 pb-8 -mt-20 relative">
                        <div className="flex flex-col md:flex-row items-end md:items-end gap-6 mb-6">
                            <Avatar className="w-32 h-32 border-4 border-background shadow-xl">
                                <AvatarImage src={creator.avatar as string | undefined} />
                                <AvatarFallback className="text-4xl">{String(creator.name ?? "")[0]}</AvatarFallback>
                            </Avatar>

                            <div className="flex-1 pb-2">
                                <div className="flex items-center gap-2 mb-1">
                                    <h2 className="text-3xl font-bold">{String(creator.name ?? "")}</h2>
                                    {Boolean(creator.verified) && <CheckCircle className="w-6 h-6 fill-blue-500 text-white" />}
                                </div>
                                <div className="flex flex-wrap items-center gap-4 text-muted-foreground">
                                    <span className="text-lg">@{String(creator.handle ?? "")}</span>
                                    <Badge variant="secondary" className="px-3 py-1 text-sm font-medium">
                                        {String(creator.niche ?? "")}
                                    </Badge>
                                    <div className="flex items-center gap-1 text-sm">
                                        <MapPin className="w-4 h-4" />
                                        {String(creator.location ?? "")}
                                    </div>
                                </div>
                            </div>

                            <div className="flex gap-3 pb-2 w-full md:w-auto">
                                <Button className="flex-1 md:flex-none shadow-sm">Contact</Button>
                                <Button variant="outline" size="icon" className="shadow-sm">
                                    <Mail className="w-4 h-4" />
                                </Button>
                            </div>
                        </div>

                        <Tabs defaultValue="overview" className="w-full">
                            <TabsList className="w-full justify-start h-auto p-1 bg-muted/50 mb-6">
                                <TabsTrigger value="overview" className="py-2.5 px-6">Overview</TabsTrigger>
                                <TabsTrigger value="content" className="py-2.5 px-6">Content</TabsTrigger>
                                <TabsTrigger value="analytics" className="py-2.5 px-6">Analytics</TabsTrigger>
                            </TabsList>

                            <TabsContent value="overview" className="space-y-8 animate-in fade-in-0 slide-in-from-left-4 duration-300">

                                {/* Stats Grid */}
                                <div className="grid grid-cols-3 gap-4">
                                    <Card className="bg-primary/5 border-primary/10 shadow-sm hover:shadow-md transition-shadow">
                                        <CardContent className="p-6 text-center">
                                            <div className="text-3xl font-bold text-primary mb-1">{String((creator.stats as Record<string, unknown>)?.followers ?? "")}</div>
                                            <div className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Followers</div>
                                        </CardContent>
                                    </Card>
                                    <Card className="bg-primary/5 border-primary/10 shadow-sm hover:shadow-md transition-shadow">
                                        <CardContent className="p-6 text-center">
                                            <div className="text-3xl font-bold text-primary mb-1">{String((creator.stats as Record<string, unknown>)?.engagement ?? "")}</div>
                                            <div className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Engagement</div>
                                        </CardContent>
                                    </Card>
                                    <Card className="bg-primary/5 border-primary/10 shadow-sm hover:shadow-md transition-shadow">
                                        <CardContent className="p-6 text-center">
                                            <div className="text-3xl font-bold text-primary mb-1">{String((creator.stats as Record<string, unknown>)?.posts ?? "")}</div>
                                            <div className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Avg. Reach</div>
                                        </CardContent>
                                    </Card>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                                    <div className="md:col-span-2 space-y-6">
                                        <div>
                                            <h3 className="text-lg font-semibold mb-3">About</h3>
                                            <p className="text-muted-foreground leading-7">
                                                Passionate content creator sharing insights about <span className="font-medium text-foreground">{String(creator.niche ?? "").toLowerCase()}</span>.
                                                Consistency and authenticity are key to my growth.
                                                I create high-quality content that resonates with my audience and drives meaningful engagement.
                                                Looking for collaborations with brands that align with my values and aesthetics.
                                            </p>
                                        </div>

                                        <div>
                                            <h3 className="text-lg font-semibold mb-3">Social Channels</h3>
                                            <div className="flex gap-4">
                                                <div className="flex items-center gap-3 p-3 border rounded-lg flex-1 hover:bg-accent/50 transition-colors cursor-pointer">
                                                    <div className="p-2 bg-pink-100 dark:bg-pink-900/30 rounded-full text-pink-600">
                                                        <Instagram className="w-5 h-5" />
                                                    </div>
                                                    <div>
                                                        <div className="font-medium">Instagram</div>
                                                        <div className="text-xs text-muted-foreground">@sarahj_style</div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-3 p-3 border rounded-lg flex-1 hover:bg-accent/50 transition-colors cursor-pointer">
                                                    <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-full text-blue-500">
                                                        <Twitter className="w-5 h-5" />
                                                    </div>
                                                    <div>
                                                        <div className="font-medium">Twitter</div>
                                                        <div className="text-xs text-muted-foreground">@sarahj_tweets</div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="space-y-6">
                                        <Card>
                                            <CardContent className="p-5 space-y-4">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm text-muted-foreground">Joined</span>
                                                    <span className="font-medium flex items-center gap-2">
                                                        <Calendar className="w-4 h-4 text-muted-foreground" />
                                                        Mar 2023
                                                    </span>
                                                </div>
                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm text-muted-foreground">Language</span>
                                                    <span className="font-medium">English</span>
                                                </div>
                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm text-muted-foreground">Response Time</span>
                                                    <span className="font-medium">~24 Hours</span>
                                                </div>
                                            </CardContent>
                                        </Card>
                                    </div>
                                </div>
                            </TabsContent>

                            <TabsContent value="content" className="animate-in fade-in-0 slide-in-from-right-4 duration-300">
                                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                                    {[1, 2, 3, 4, 5, 6].map((i) => (
                                        <div key={i} className="aspect-square bg-muted rounded-xl overflow-hidden relative group cursor-pointer">
                                            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white font-medium gap-2">
                                                <BarChart3 className="w-5 h-5" />
                                                <span>4.2k</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </TabsContent>

                            <TabsContent value="analytics" className="animate-in fade-in-0 slide-in-from-right-4 duration-300">
                                <div className="h-64 flex items-center justify-center border-2 border-dashed rounded-xl text-muted-foreground">
                                    Analytics Placeholder
                                </div>
                            </TabsContent>
                        </Tabs>
                    </div>
                </motion.div>
            </SheetContent>
        </Sheet>
    )
}

export default ProfileSidebar