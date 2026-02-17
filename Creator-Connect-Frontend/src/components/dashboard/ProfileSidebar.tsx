
"use client"

import React, { useEffect, useState } from 'react'
import {
    Sheet,
    SheetContent,
    SheetTitle,
    SheetClose,
} from "@/components/ui/sheet"
import { X } from "lucide-react"
import { getInfluencerWithFallback } from '@/services/results.service'
import { toast } from "sonner";
import { generateUnifiedReport } from '@/services/report.service'
import { getIndustryStandards, type IndustryComparisonStatus } from '@/services/industry-standards.service'
import ProfileSidebarContent from './ProfileSidebarContent'

// Imported Visual Components

interface ProfileSidebarProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
    creator: Record<string, unknown> | null
    conversationId?: string | null
}

const ProfileSidebar = ({ isOpen, onOpenChange, creator, conversationId }: ProfileSidebarProps) => {
    const [detailedCreator, setDetailedCreator] = useState<Record<string, unknown> | null>(null);
    const [loading, setLoading] = useState(false);
    const [pdfLoading, setPdfLoading] = useState(false);
    const [allResults, setAllResults] = useState<Record<string, unknown>[]>([]);
    const [, setIndustryPeersReady] = useState(false);
    const [, setIndustryComparisonStatus] = useState<IndustryComparisonStatus | null>(null);
    const [isPolling, setIsPolling] = useState(false);
    const pollingIntervalRef = React.useRef<NodeJS.Timeout | null>(null);

    const handleGeneratePdf = async () => {
        try {
            setPdfLoading(true);
            const activeCreator = detailedCreator || creator; // Fallback to prop if detailed not ready
            if (!activeCreator) return;

            const influencerId = activeCreator.id || activeCreator._id;
            if (!influencerId) {
                toast.error("Error", { description: "Influencer ID not found" });
                return;
            }

            const res = await generateUnifiedReport({
                influencerId: String(influencerId),
                conversationId: (activeCreator.conversation_id as string | null) ?? null
            });

            if (res.ok) {
                toast.success("Success", { description: "Report downloaded successfully" });
            } else {
                toast.error("Error", { description: "Failed to generate report" });
            }
        } catch (error) {
            console.error(error);
            toast.error("Error", { description: error instanceof Error ? error.message : "Failed to generate report" });
        } finally {
            setPdfLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen && creator?.id) {
            const influencerId = String(creator.id);
            const fetchDetails = async () => {
                setLoading(true);
                try {
                    const data = await getInfluencerWithFallback(influencerId, conversationId ?? undefined);
                    if (data?.influencer) {
                        setDetailedCreator(data.influencer);
                    } else if (data) {
                        setDetailedCreator(data);
                    }
                } catch (err) {
                    console.error("Failed to fetch detailed creator info:", err);
                } finally {
                    setLoading(false);
                }
            };

            const fetchComparisonData = async () => {
                if (!conversationId) return;

                try {
                    const base = process.env.NEXT_PUBLIC_API_URL || "";
                    const allResultsUrl = `${base}/api/results/dynamic/prompt/all?conversation_id=${conversationId}`;
                    const res = await fetch(allResultsUrl, {
                        method: "GET",
                        headers: { accept: "application/json" },
                    });

                    if (res.ok) {
                        const data = await res.json();
                        if (data.results && Array.isArray(data.results)) {
                            setAllResults(data.results);

                            // Check if industry peers are already ready
                            const hasIndustryPeers = data.results.some((r: Record<string, unknown>) => r.industry_standard === true);
                            const peerCount = data.results.filter((r: Record<string, unknown>) => r.industry_standard === true).length;

                            if (hasIndustryPeers && peerCount >= 2) {
                            } else {
                                startPolling(conversationId);
                            }
                        }
                    }
                } catch (err) {
                    console.error("Error fetching comparison data:", err);
                }
            };

            const startPolling = (cid: string) => {
                if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current);

                setIsPolling(true);
                pollingIntervalRef.current = setInterval(async () => {
                    try {
                        const statusData = await getIndustryStandards(cid);
                        if (statusData.industry_comparison) {
                            setIndustryComparisonStatus(statusData.industry_comparison);
                        }

                        if (statusData.status === "completed" || statusData.industry_comparison?.status === "completed") {
                            // Fetch updated results
                            const base = process.env.NEXT_PUBLIC_API_URL || "";
                            const allResultsUrl = `${base}/api/results/dynamic/prompt/all?conversation_id=${cid}`;
                            const res = await fetch(allResultsUrl);
                            if (res.ok) {
                                const data = await res.json();
                                if (data.results) {
                                    setAllResults(data.results);
                                    setIndustryPeersReady(true);
                                    stopPolling();
                                }
                            }
                        } else if (statusData.status === "error" || statusData.industry_comparison?.status === "failed") {
                            stopPolling();
                        }
                    } catch (e) {
                        console.error("Polling error:", e);
                    }
                }, 5000);
            };

            const stopPolling = () => {
                if (pollingIntervalRef.current) {
                    clearInterval(pollingIntervalRef.current);
                    pollingIntervalRef.current = null;
                }
                setIsPolling(false);
            };

            fetchDetails();
            fetchComparisonData();

            return () => {
                stopPolling();
            };
        } else {
            setDetailedCreator(null);
            setAllResults([]);
            setIndustryPeersReady(false);
        }
    }, [isOpen, creator, conversationId]);

    if (!creator) return null

    const resolvedCreator = detailedCreator || creator;
    const isLoading = loading && !detailedCreator;


    return (
        <Sheet open={isOpen} onOpenChange={onOpenChange}>
            {/* Increased width and improved backdrop */}
            <SheetContent
                side="right"
                className="w-full sm:max-w-[70%] sm:w-[70%] p-0 border-l border-white/20 dark:border-white/10 shadow-2xl overflow-hidden flex flex-col"
            >
                <SheetTitle className="sr-only">Creator Profile Details</SheetTitle>
                {/* Action Buttons */}
                <div className="absolute top-4 right-4 z-50 flex items-center gap-2">
                    <SheetClose className="p-2 rounded-full bg-white/20 hover:bg-white/40 backdrop-blur-md text-gray-900 dark:text-white transition-all ring-0 focus:ring-0 outline-none">
                        <X className="w-5 h-5" />
                        <span className="sr-only">Close</span>
                    </SheetClose>
                </div>

                {/* Main Scrollable Content */}
                <div className="relative z-10 flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin scrollbar-thumb-gray-200 dark:scrollbar-thumb-gray-800">
                    <div className="p-6 md:p-10 pt-16 space-y-8">
                        <ProfileSidebarContent
                            creator={resolvedCreator}
                            isLoading={isLoading}
                            pdfLoading={pdfLoading}
                            onDownloadPdf={handleGeneratePdf}
                            allResults={allResults}
                            isPolling={isPolling}
                        />
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    )
}

export default ProfileSidebar
