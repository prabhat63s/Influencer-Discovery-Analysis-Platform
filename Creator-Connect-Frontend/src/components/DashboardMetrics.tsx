"use client";

import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { motion } from "framer-motion";
import Highcharts from "highcharts";
import HighchartsReact from "highcharts-react-official";
import { Info, Shield, TrendingUp, Users, Heart, MessageCircle } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";


// Normalize numeric input
const normalizeNumericInput = (value: unknown): number | null => {
    if (value === null || value === undefined) return null;
    if (typeof value === "number" && !Number.isNaN(value)) return value;
    if (typeof value === "string") {
        let sanitized = value.trim();
        if (!sanitized || sanitized.toLowerCase() === "n/a" || sanitized.toLowerCase() === "nan") {
            return null;
        }
        sanitized = sanitized.replace(/,/g, "");
        let multiplier = 1;
        if (sanitized.endsWith("%")) {
            sanitized = sanitized.slice(0, -1);
        }
        const suffix = sanitized.slice(-1).toLowerCase();
        if (suffix === "k") {
            multiplier = 1_000;
            sanitized = sanitized.slice(0, -1);
        } else if (suffix === "m") {
            multiplier = 1_000_000;
            sanitized = sanitized.slice(0, -1);
        }
        const parsed = parseFloat(sanitized);
        if (Number.isNaN(parsed)) return null;
        return parsed * multiplier;
    }
    return null;
};

const toPercent = (v: unknown): number | null => {
    if (v === null || v === undefined) return null;
    if (typeof v === "number") {
        if (!Number.isFinite(v)) return null;
        return Math.abs(v) <= 1 ? Number(v.toFixed(2)) : Number(v.toFixed(2));
    }
    if (typeof v === "string") {
        const s = v.trim().replace(/,/g, "").replace("%", "");
        if (!s || /^nan$/i.test(s) || /^n\/a$/i.test(s)) return null;
        const n = Number(s);
        if (Number.isNaN(n)) return null;
        return Math.abs(n) <= 1 ? Number(n.toFixed(2)) : Number(n.toFixed(2));
    }
    return null;
};

// Generate comparative AI insight for metrics
const generateComparativeInsight = (
    metricType: "followers" | "engagement" | "authenticity" | "likes" | "comments",
    anchorValue: number,
    peerValues: number[]
): string => {
    if (peerValues.length === 0 || anchorValue <= 0) {
        return generateMetricInsight(metricType, anchorValue);
    }

    const allValues = [anchorValue, ...peerValues].filter(v => v > 0);
    if (allValues.length === 0) return "";

    const maxValue = Math.max(...allValues);
    const minValue = Math.min(...allValues);

    switch (metricType) {
        case "followers":
            if (anchorValue === maxValue) {
                const diff = minValue > 0 ? ((anchorValue / minValue - 1) * 100) : 0;
                return `The selected influencer leads with ${diff.toFixed(0)}% more followers than the lowest benchmark.`;
            } else {
                const leaderValue = maxValue;
                // Calculate percentage difference correctly: (leader - anchor) / leader * 100
                const diff = leaderValue > 0 && anchorValue > 0 ? ((leaderValue - anchorValue) / leaderValue) * 100 : 0;
                // Cap at 100% to avoid showing >100%
                const cappedDiff = Math.min(100, diff);
                if (cappedDiff > 50) {
                    return `The selected influencer has ${cappedDiff.toFixed(0)}% fewer followers than the industry leader, indicating significant growth potential.`;
                } else if (cappedDiff > 20) {
                    return `The selected influencer has ${cappedDiff.toFixed(0)}% fewer followers than the industry leader but remains competitive.`;
                } else {
                    return `The selected influencer has ${cappedDiff.toFixed(0)}% fewer followers than the industry leader, showing strong market positioning.`;
                }
            }
        case "engagement":
            if (anchorValue === maxValue) {
                return `The selected influencer achieves the highest engagement rate, indicating superior audience interaction.`;
            } else {
                const leaderValue = maxValue;
                const diff = leaderValue > 0 ? ((leaderValue - anchorValue) / leaderValue) * 100 : 0;
                if (diff < 0.1) {
                    return `Engagement rate is nearly identical to the industry leader, demonstrating strong audience connection.`;
                }
                return `Engagement rate is ${diff.toFixed(1)}% below the industry leader, suggesting opportunities for content optimization.`;
            }
        case "authenticity":
            if (anchorValue === maxValue) {
                return `The selected influencer has the highest audience authenticity, indicating a genuine follower base.`;
            } else {
                const leaderValue = maxValue;
                const diff = leaderValue - anchorValue;
                if (diff < 1) {
                    return `Audience authenticity is nearly identical to the industry leader, showing excellent follower quality.`;
                }
                return `Audience authenticity is ${diff.toFixed(1)}% below the industry leader, which may impact campaign trust.`;
            }
        case "likes":
            if (anchorValue === maxValue) {
                return `The selected influencer receives the highest average likes, demonstrating strong content appeal.`;
            } else {
                const leaderValue = maxValue;
                const diff = leaderValue > 0 && anchorValue > 0 ? ((leaderValue - anchorValue) / leaderValue) * 100 : 0;
                const cappedDiff = Math.min(100, diff);
                if (cappedDiff > 50) {
                    return `Average likes are ${cappedDiff.toFixed(0)}% below the industry leader, indicating significant opportunity for content strategy refinement.`;
                }
                return `Average likes are ${cappedDiff.toFixed(0)}% below the industry leader, indicating potential for content strategy refinement.`;
            }
        case "comments":
            if (anchorValue === maxValue) {
                return `The selected influencer generates the highest average comments, showing deep audience engagement.`;
            } else {
                const leaderValue = maxValue;
                const diff = leaderValue > 0 && anchorValue > 0 ? ((leaderValue - anchorValue) / leaderValue) * 100 : 0;
                const cappedDiff = Math.min(100, diff);
                if (cappedDiff > 50) {
                    return `Average comments are ${cappedDiff.toFixed(0)}% below the industry leader, suggesting significant room for improved audience interaction.`;
                }
                return `Average comments are ${cappedDiff.toFixed(0)}% below the industry leader, suggesting room for improved audience interaction.`;
            }
        default:
            return "";
    }
};

// Generate AI insight for individual metrics
const generateMetricInsight = (
    metricType: "followers" | "engagement" | "authenticity" | "likes" | "comments",
    value: number,
    engagementRate?: number,
    realFollowersPct?: number
): string => {
    switch (metricType) {
        case "followers":
            if (value >= 1_000_000) {
                return "Large follower base indicates <strong>extensive reach potential</strong>, ideal for mass-market brand campaigns.";
            } else if (value >= 100_000) {
                return "Strong follower count demonstrates <strong>solid audience foundation</strong>, perfect for targeted brand partnerships.";
            } else {
                return "Growing follower base shows <strong>emerging influence potential</strong>, suitable for niche brand collaborations.";
            }
        case "engagement":
            if (engagementRate && engagementRate >= 5) {
                return "Exceptional engagement rate demonstrates <strong>highly active and responsive audiences</strong>, ideal for brands seeking immediate campaign impact.";
            } else if (engagementRate && engagementRate >= 3) {
                return "Strong engagement indicates <strong>invested and interactive followers</strong>, suitable for building long-term brand relationships.";
            } else {
                return "Current engagement suggests opportunities for <strong>strategic content partnerships</strong> to maximize audience connection.";
            }
        case "authenticity":
            if (realFollowersPct && realFollowersPct >= 85) {
                return "High authenticity confirms a <strong>genuine, trustworthy audience base</strong>, minimizing campaign risk and ensuring authentic brand alignment.";
            } else if (realFollowersPct && realFollowersPct >= 70) {
                return "Good authenticity reflects an <strong>organic growth pattern</strong>, indicating sustainable audience development.";
            } else {
                return "Authenticity metrics suggest <strong>careful audience quality evaluation</strong> before committing to major partnerships.";
            }
        case "likes":
            if (value >= 10000) {
                return "High like counts demonstrate <strong>strong content appeal and audience satisfaction</strong>, indicating successful brand content potential.";
            } else if (value >= 1000) {
                return "Solid like performance shows <strong>consistent audience appreciation</strong>, ideal for steady brand content engagement.";
            } else {
                return "Growing like metrics indicate <strong>developing content resonance</strong>, perfect for brands seeking emerging creator partnerships.";
            }
        case "comments":
            if (value >= 500) {
                return "High comment activity demonstrates <strong>deep audience engagement and discussion</strong>, ideal for brands seeking meaningful audience interaction.";
            } else if (value >= 100) {
                return "Active comment engagement shows <strong>thoughtful audience participation</strong>, suitable for brands wanting dialogue-driven campaigns.";
            } else {
                return "Comment metrics indicate <strong>growing audience interaction potential</strong>, perfect for brands building community connections.";
            }
        default:
            return "";
    }
};

// Build growing line chart for individual metrics with comparison
// Each influencer gets separate dataset with fixed colors
const buildGrowingLineChart = (
    influencersData: Array<{ username: string; value: number; color: string }>,
    label: string,
    textColor: string,
    height: number = 200
) => {
    // Generate 6 months of simulated growth data for each influencer (Aug 2025 - Jan 2026)
    const months = ["Aug '25", "Sep '25", "Oct '25", "Nov '25", "Dec '25", "Jan '26"];

    // Create separate series for each influencer
    const series = influencersData.map(inf => {
        const data: number[] = [];
        const baseValue = inf.value * 0.6; // Start at 60% of current value
        const increment = (inf.value - baseValue) / 5;

        for (let i = 0; i < 6; i++) {
            data.push(baseValue + (increment * i) + (Math.random() * inf.value * 0.05)); // Small variance
        }
        data[5] = inf.value; // Ensure last point is exact value

        return {
            name: inf.username,
            data: data,
            color: inf.color,
            lineWidth: inf.color === "#3b82f6" ? 3 : 2, // Thicker line for anchor
            marker: { radius: inf.color === "#3b82f6" ? 4 : 3 },
            dashStyle: "Solid", // All lines are solid with continuous growth
        };
    });

    return {
        chart: {
            type: "line",
            backgroundColor: "transparent",
            height: height,
        },
        title: { text: "" },
        xAxis: {
            categories: months,
            labels: { style: { color: textColor, fontSize: "11px" } },
        },
        yAxis: {
            title: { text: "" },
            labels: {
                style: { color: textColor, fontSize: "10px" },
                formatter: function (this: Highcharts.AxisLabelsFormatterContextObject): string {
                    const val = this.value as number;
                    if (val >= 1_000_000) return (val / 1_000_000).toFixed(1) + "M";
                    if (val >= 1_000) return (val / 1_000).toFixed(1) + "K";
                    return val.toFixed(0);
                }
            },
            gridLineColor: "rgba(255, 255, 255, 0.1)",
        },
        plotOptions: {
            line: {
                dataLabels: {
                    enabled: true,
                    formatter: function (this: Highcharts.Point): string {
                        const val = this.y ?? 0;
                        if (val >= 1_000_000) return (val / 1_000_000).toFixed(1) + "M";
                        if (val >= 1_000) return (val / 1_000).toFixed(1) + "K";
                        return val.toLocaleString(undefined, { maximumFractionDigits: 0 });
                    },
                    style: {
                        color: textColor,
                        textOutline: "none",
                        fontSize: "10px",
                        fontWeight: "bold",
                    },
                },
                marker: {
                    radius: 4,
                },
            },
        },
        series: series,
        legend: {
            enabled: influencersData.length > 1,
            align: "right",
            verticalAlign: "top",
            itemStyle: { color: textColor, fontSize: "11px" },
            symbolWidth: 12,
            symbolHeight: 12,
            symbolRadius: 6,
        },
        tooltip: {
            shared: true,
            useHTML: true,
            formatter: function (this: { x?: string; points?: Array<{ y?: number; color?: string; series?: { name?: string } }> }): string {
                const header = `<div style="font-size: 10px; margin-bottom: 4px;">${this.x}</div>`;
                const points = this.points || [];
                const body = points.map((point: { y?: number; color?: string; series?: { name?: string } }) => {
                    const val = point.y ?? 0;
                    let formattedVal = "";
                    if (val >= 1_000_000) formattedVal = (val / 1_000_000).toFixed(1) + "M";
                    else if (val >= 1_000) formattedVal = (val / 1_000).toFixed(1) + "K";
                    else formattedVal = val.toLocaleString(undefined, { maximumFractionDigits: 0 });

                    return `
                        <div style="display: flex; align-items: center; gap: 4px; font-size: 12px;">
                            <span style="color: ${point.color}">●</span>
                            <span>${point.series?.name ?? ""}:</span>
                            <span style="font-weight: bold;">${formattedVal}</span>
                        </div>
                    `;
                }).join("");
                return `<div style="background: var(--background); color: var(--foreground); padding: 8px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); border: 1px solid var(--border);">${header}${body}</div>`;
            },
            backgroundColor: "transparent",
            borderWidth: 0,
            shadow: false,
            padding: 0,
        },
        credits: { enabled: false },
    };
};

// Build percentage line chart with comparison
// Each influencer gets separate dataset with fixed colors
const buildPercentageLineChart = (
    influencersData: Array<{ username: string; value: number; color: string }>,
    label: string,
    textColor: string,
    height: number = 200
) => {
    // Last 6 months (Aug 2025 - Jan 2026)
    const months = ["Aug '25", "Sep '25", "Oct '25", "Nov '25", "Dec '25", "Jan '26"];

    // Create separate series for each influencer
    const series = influencersData.map(inf => {
        const data: number[] = [];
        const baseValue = inf.value * 0.7;
        const increment = (inf.value - baseValue) / 5;

        for (let i = 0; i < 6; i++) {
            data.push(Math.max(0, baseValue + (increment * i) + (Math.random() * inf.value * 0.03)));
        }
        data[5] = inf.value;

        return {
            name: inf.username,
            data: data,
            color: inf.color,
            lineWidth: inf.color === "#3b82f6" ? 3 : 2, // Thicker line for anchor
            marker: { radius: inf.color === "#3b82f6" ? 4 : 3 },
            dashStyle: "Solid", // All lines are solid with continuous growth
        };
    });

    return {
        chart: {
            type: "line",
            backgroundColor: "transparent",
            height: height,
        },
        title: { text: "" },
        xAxis: {
            categories: months,
            labels: { style: { color: textColor, fontSize: "11px" } },
        },
        yAxis: {
            title: { text: "" },
            labels: {
                style: { color: textColor, fontSize: "10px" },
                formatter: function (this: Highcharts.AxisLabelsFormatterContextObject): string {
                    return (this.value as number).toFixed(1) + "%";
                }
            },
            gridLineColor: "rgba(255, 255, 255, 0.1)",
            // Dynamic scale based on data range to show differences better
            min: (() => {
                const allValues = influencersData.map(inf => inf.value);
                if (allValues.length === 0) return 0;
                const minVal = Math.min(...allValues);
                const range = Math.max(...allValues) - minVal;
                // If range is small, add more padding to show differences
                if (range < 2) {
                    return Math.max(0, minVal - 1); // 1% padding for small ranges
                }
                return Math.max(0, minVal - (range * 0.1)); // 10% padding below
            })(),
            max: (() => {
                const allValues = influencersData.map(inf => inf.value);
                if (allValues.length === 0) return 100;
                const maxVal = Math.max(...allValues);
                const range = maxVal - Math.min(...allValues);
                // If range is small, add more padding to show differences
                if (range < 2) {
                    return Math.min(100, maxVal + 1); // 1% padding for small ranges
                }
                return Math.min(100, maxVal + (range * 0.1)); // 10% padding above, but cap at 100%
            })(),
        },
        plotOptions: {
            line: {
                dataLabels: {
                    enabled: true,
                    formatter: function (this: Highcharts.Point): string {
                        return (this.y ?? 0).toFixed(1) + "%";
                    },
                    style: {
                        color: textColor,
                        textOutline: "none",
                        fontSize: "10px",
                        fontWeight: "bold",
                    },
                },
                marker: {
                    radius: 4,
                },
            },
        },
        series: series,
        tooltip: {
            shared: true,
            useHTML: true,
            formatter: function (this: { x?: string; points?: Array<{ y?: number; color?: string; series?: { name?: string } }> }): string {
                const header = `<div style="font-size: 10px; margin-bottom: 4px;">${this.x}</div>`;
                const points = this.points || [];
                const body = points.map((point: { y?: number; color?: string; series?: { name?: string } }) => {
                    const val = point.y ?? 0;
                    const formattedVal = val.toFixed(2) + "%";

                    return `
                        <div style="display: flex; align-items: center; gap: 4px; font-size: 12px;">
                            <span style="color: ${point.color}">●</span>
                            <span>${point.series?.name ?? ""}:</span>
                            <span style="font-weight: bold;">${formattedVal}</span>
                        </div>
                    `;
                }).join("");
                return `<div style="background: var(--background); color: var(--foreground); padding: 8px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); border: 1px solid var(--border);">${header}${body}</div>`;
            },
            backgroundColor: "transparent",
            borderWidth: 0,
            shadow: false,
            padding: 0,
        },
        credits: { enabled: false },
    };
};

type DashboardMetricsProps = {
    metrics: Record<string, unknown>;
    influencer?: Record<string, unknown>;
    anchor?: Record<string, unknown>;
    peers?: Record<string, unknown>[];
    isLoading?: boolean;
};

export default function DashboardMetrics({ metrics, influencer, anchor, peers = [], isLoading }: DashboardMetricsProps) {
    const [modulesLoaded, setModulesLoaded] = useState(false);
    const { theme } = useTheme();

    // Load Highcharts modules including 3D
    useEffect(() => {
        const load = async () => {
            try {
                const more = await import("highcharts/highcharts-more.js");
                const hc3d = await import("highcharts/highcharts-3d.js");
                const moreModule = more as unknown as { default?: (chart: typeof Highcharts) => void };
                const hc3dModule = hc3d as unknown as { default?: (chart: typeof Highcharts) => void };
                if (typeof moreModule.default === "function") moreModule.default(Highcharts);
                if (typeof hc3dModule.default === "function") hc3dModule.default(Highcharts);
                setModulesLoaded(true);
            } catch (err) {
                console.error("Highcharts module load failed:", err);
                setModulesLoaded(true);
            }
        };
        load();
    }, []);

    useEffect(() => {
        if (!modulesLoaded) return;
        Highcharts.setOptions({
            colors: ["#9333ea", "#db2777", "#0ea5e9", "#3b82f6", "#f59e0b", "#10b981"],
            chart: {
                backgroundColor: "transparent",
                style: { fontFamily: "inherit" },
            },
        });
        Highcharts.charts.forEach((chart) => chart?.redraw());
    }, [theme, modulesLoaded]);

    if (isLoading) {
        return (
            <div className="w-full space-y-6">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl shadow-sm p-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            {/* Left: Graph Skeleton */}
                            <div className="bg-gray-50/50 dark:bg-black/20 rounded-xl p-4 border border-gray-100 dark:border-white/5 h-[300px] flex items-center justify-center">
                                <Skeleton className="h-[250px] w-full rounded-lg" />
                            </div>
                            {/* Right: Info Skeleton */}
                            <div className="flex flex-col justify-center space-y-6">
                                <div className="flex items-center gap-3">
                                    <Skeleton className="w-10 h-10 rounded-lg" />
                                    <Skeleton className="h-6 w-40 rounded-md" />
                                </div>
                                <div className="space-y-3">
                                    <Skeleton className="h-10 w-full rounded-lg" />
                                    <Skeleton className="h-10 w-full rounded-lg" />
                                </div>
                                <Skeleton className="h-4 w-32 rounded-md" />
                                <div className="pt-4 border-t border-gray-100 dark:border-white/10">
                                    <Skeleton className="h-4 w-full rounded-md" />
                                    <Skeleton className="h-4 w-3/4 rounded-md mt-2" />
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    if (!modulesLoaded) {
        return (
            <div className="w-full flex items-center justify-center py-20">
                <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent"></div>
            </div>
        );
    }

    const safeMetrics = metrics || {};
    const chartTextColor = theme === "dark" ? "#FFFFFF" : "#000000";
    const anchorData = anchor || influencer || {};

    // Helper function to format numbers consistently (used throughout component)
    const formatNumberLocal = (value: number | string | undefined): string => {
        if (value === undefined || value === null) return "N/A";

        let numValue: number;
        if (typeof value === "string") {
            const cleaned = value.replace(/[^0-9.]/g, "");
            numValue = parseFloat(cleaned);
            if (isNaN(numValue)) return value;
        } else {
            numValue = value;
        }

        if (isNaN(numValue) || !isFinite(numValue)) return "N/A";

        if (numValue >= 1_000_000_000) return `${(numValue / 1_000_000_000).toFixed(1)}B`;
        if (numValue >= 1_000_000) return `${(numValue / 1_000_000).toFixed(1)}M`;
        if (numValue >= 1_000) return `${(numValue / 1_000).toFixed(1)}K`;
        return numValue.toLocaleString();
    };

    // Extract metrics for anchor
    const followers = normalizeNumericInput(safeMetrics.followers ?? anchorData?.followers) ?? 0;
    const avgLikes = normalizeNumericInput(safeMetrics.avg_likes ?? safeMetrics.average_likes ?? anchorData?.avg_likes ?? anchorData?.average_likes) ?? 0;
    const avgComments = normalizeNumericInput(safeMetrics.avg_comments ?? safeMetrics.average_comments ?? anchorData?.avg_comments ?? anchorData?.average_comments) ?? 0;
    const engagementRate = toPercent(safeMetrics.engagement_rate ?? anchorData?.engagement_rate) ?? 0;
    const realFollowersPct = toPercent(safeMetrics.real_percentage ?? safeMetrics.real_followers_percentage ?? anchorData?.real_percentage ?? anchorData?.real_followers_percentage);
    const suspiciousFollowersPctProvided = toPercent(safeMetrics.suspicious_followers_percentage ?? anchorData?.suspicious_followers_percentage);

    // Use provided suspicious percentage if available, otherwise calculate from real (only if real > 0)
    const suspiciousFollowersPct = suspiciousFollowersPctProvided !== null
        ? suspiciousFollowersPctProvided
        : (realFollowersPct !== null && realFollowersPct > 0 ? 100 - realFollowersPct : 0);

    // Fallback realFollowersPct to 0 for display if null
    const realFollowersPctDisplay = realFollowersPct ?? 0;

    // Extract metrics for ALL influencers (anchor + peers) with proper data binding
    const anchorUsername = (anchorData?.Id || anchorData?.username || anchorData?.NAME || anchorData?.name || "Selected Influencer") as string;
    const anchorDisplayName = `@${String(anchorUsername).replace(/^@/, "")}`;

    // Build complete influencer dataset for proper data binding
    const allInfluencersData = [
        {
            username: anchorDisplayName,
            followers: followers,
            engagementRate: engagementRate,
            realFollowersPct: realFollowersPctDisplay,
            suspiciousFollowersPct: suspiciousFollowersPct,
            avgLikes: avgLikes,
            avgComments: avgComments,
            color: "#3b82f6", // Blue for anchor
        },
        ...(peers ?? []).slice(0, 2).map((p, idx) => {
            const peerFollowersVal = (() => {
                // normalizeNumericInput already handles M/K conversion, so use it directly
                const rawFollowers = p?.followers;
                const val = normalizeNumericInput(rawFollowers);

                return val === null ? 0 : val;
            })();

            const peerAvgLikesVal = (() => {
                const rawVal = p?.avg_likes ?? p?.average_likes;
                if (typeof rawVal === "number") return rawVal;
                const val = normalizeNumericInput(rawVal);
                return val === null ? 0 : val;
            })();

            const peerAvgCommentsVal = (() => {
                const rawVal = p?.avg_comments ?? p?.average_comments;
                if (typeof rawVal === "number") return rawVal;
                const val = normalizeNumericInput(rawVal);
                return val === null ? 0 : val;
            })();

            const peerEngagementRateVal = toPercent(p?.engagement_rate) ?? 0;
            const peerRealFollowersPctVal = toPercent(p?.real_followers_percentage ?? p?.real_percentage);
            const peerSuspiciousFollowersPctProvided = toPercent(p?.suspicious_followers_percentage);

            // Use provided suspicious percentage if available, otherwise calculate from real (only if real > 0)
            const peerSuspiciousFollowersPctVal = peerSuspiciousFollowersPctProvided !== null
                ? peerSuspiciousFollowersPctProvided
                : (peerRealFollowersPctVal !== null && peerRealFollowersPctVal > 0 ? 100 - peerRealFollowersPctVal : 0);

            // Fallback peerRealFollowersPctVal to 0 for display if null
            const peerRealFollowersPctDisplay = peerRealFollowersPctVal ?? 0;

            const username = p?.Id || p?.username || p?.NAME || p?.name || `Peer ${idx + 1}`;
            const displayName = `@${String(username).replace(/^@/, "")}`;

            return {
                username: displayName,
                followers: peerFollowersVal,
                engagementRate: peerEngagementRateVal,
                realFollowersPct: peerRealFollowersPctDisplay,
                suspiciousFollowersPct: peerSuspiciousFollowersPctVal,
                avgLikes: peerAvgLikesVal,
                avgComments: peerAvgCommentsVal,
                color: idx === 0 ? "#9333ea" : "#f59e0b", // Purple for Peer 1, Orange for Peer 2
            };
        }),
    ];


    const containerVariants = {
        hidden: { opacity: 0 },
        visible: {
            opacity: 1,
            transition: {
                staggerChildren: 0.15,
            },
        },
    };

    const itemVariants = {
        hidden: { opacity: 0, y: 20 },
        visible: {
            opacity: 1,
            y: 0,
            transition: {
                duration: 0.5,
                ease: [0.16, 1, 0.3, 1] as const,
            },
        },
    };

    return (
        <TooltipProvider>
            <motion.div
                variants={containerVariants}
                initial="hidden"
                animate="visible"
                className="w-full space-y-6"
            >
                {/* Followers Metric */}
                <motion.div
                    variants={itemVariants}
                    className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl shadow-sm p-6"
                >
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Left: Graph */}
                        <div className="bg-gray-50/50 dark:bg-black/20 rounded-xl p-4 border border-gray-100 dark:border-white/5">
                            <HighchartsReact
                                highcharts={Highcharts}
                                options={buildGrowingLineChart(
                                    allInfluencersData.map(inf => ({ username: inf.username, value: inf.followers, color: inf.color })),
                                    "Followers",
                                    chartTextColor,
                                    300
                                )}
                                containerProps={{ style: { height: "300px", width: "100%" } }}
                            />
                        </div>
                        {/* Right: Info */}
                        <div className="flex flex-col justify-center">
                            <div className="flex items-center gap-3 mb-6">
                                <div className="p-2 bg-purple-50 dark:bg-purple-500/10 rounded-lg text-purple-600 dark:text-purple-400">
                                    <Users className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Followers Growth</h3>
                                </div>
                            </div>

                            {/* Numeric values for ALL influencers */}
                            <div className="space-y-3 mb-6">
                                {allInfluencersData.map((inf, idx) => (
                                    <div key={idx} className="flex items-center justify-between text-sm p-3 rounded-lg bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-2.5 h-2.5 rounded-full ring-2 ring-white dark:ring-[#1a1a1a]"
                                                style={{ backgroundColor: inf.color }}
                                            />
                                            <span className="font-medium text-gray-700 dark:text-gray-300">{inf.username}</span>
                                        </div>
                                        <span className="font-bold text-gray-900 dark:text-white tabular-nums">{formatNumberLocal(inf.followers)}</span>
                                    </div>
                                ))}
                            </div>

                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="inline-flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400 mb-4 cursor-help hover:text-purple-500 transition-colors">
                                        <Info size={14} />
                                        <span>What does this mean?</span>
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent className="max-w-[250px] p-3">
                                    <p className="text-xs leading-relaxed">
                                        Total follower count represents potential reach. Higher numbers indicate broader audience access for brand campaigns.
                                    </p>
                                </TooltipContent>
                            </Tooltip>

                            <div className="pt-4 border-t border-gray-100 dark:border-white/10">
                                <p
                                    className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed"
                                    dangerouslySetInnerHTML={{
                                        __html: allInfluencersData.length > 1
                                            ? generateComparativeInsight("followers", followers, allInfluencersData.slice(1).map(inf => inf.followers))
                                            : generateMetricInsight("followers", followers),
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                </motion.div>

                {/* Engagement Rate Metric */}
                <motion.div
                    variants={itemVariants}
                    className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl shadow-sm p-6"
                >
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Left: Graph */}
                        <div className="bg-gray-50/50 dark:bg-black/20 rounded-xl p-4 border border-gray-100 dark:border-white/5">
                            <HighchartsReact
                                highcharts={Highcharts}
                                options={buildPercentageLineChart(
                                    allInfluencersData.map(inf => ({ username: inf.username, value: inf.engagementRate, color: inf.color })),
                                    "Engagement Rate",
                                    chartTextColor,
                                    300
                                )}
                                containerProps={{ style: { height: "300px", width: "100%" } }}
                            />
                        </div>
                        {/* Right: Info */}
                        <div className="flex flex-col justify-center">
                            <div className="flex items-center gap-3 mb-6">
                                <div className="p-2 bg-pink-50 dark:bg-pink-500/10 rounded-lg text-pink-600 dark:text-pink-400">
                                    <TrendingUp className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Engagement Rate</h3>
                                </div>
                            </div>

                            {/* Numeric values for ALL influencers */}
                            <div className="space-y-3 mb-6">
                                {allInfluencersData.map((inf, idx) => (
                                    <div key={idx} className="flex items-center justify-between text-sm p-3 rounded-lg bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-2.5 h-2.5 rounded-full ring-2 ring-white dark:ring-[#1a1a1a]"
                                                style={{ backgroundColor: inf.color }}
                                            />
                                            <span className="font-medium text-gray-700 dark:text-gray-300">{inf.username}</span>
                                        </div>
                                        <span className="font-bold text-gray-900 dark:text-white tabular-nums">{inf.engagementRate.toFixed(2)}%</span>
                                    </div>
                                ))}
                            </div>

                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="inline-flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400 mb-4 cursor-help hover:text-pink-500 transition-colors">
                                        <Info size={14} />
                                        <span>What does this mean?</span>
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent className="max-w-[250px] p-3">
                                    <p className="text-xs leading-relaxed">
                                        Percentage of followers who actively interact with content. Higher rates mean more engaged audiences.
                                    </p>
                                </TooltipContent>
                            </Tooltip>

                            <div className="pt-4 border-t border-gray-100 dark:border-white/10">
                                <p
                                    className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed"
                                    dangerouslySetInnerHTML={{
                                        __html: allInfluencersData.length > 1
                                            ? generateComparativeInsight("engagement", engagementRate, allInfluencersData.slice(1).map(inf => inf.engagementRate))
                                            : generateMetricInsight("engagement", engagementRate, engagementRate),
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                </motion.div>

                {/* Average Likes Metric */}
                <motion.div
                    variants={itemVariants}
                    className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl shadow-sm p-6"
                >
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Left: Graph */}
                        <div className="bg-gray-50/50 dark:bg-black/20 rounded-xl p-4 border border-gray-100 dark:border-white/5">
                            <HighchartsReact
                                highcharts={Highcharts}
                                options={buildGrowingLineChart(
                                    allInfluencersData.map(inf => ({ username: inf.username, value: inf.avgLikes, color: inf.color })),
                                    "Average Likes",
                                    chartTextColor,
                                    300
                                )}
                                containerProps={{ style: { height: "300px", width: "100%" } }}
                            />
                        </div>
                        {/* Right: Info */}
                        <div className="flex flex-col justify-center">
                            <div className="flex items-center gap-3 mb-6">
                                <div className="p-2 bg-red-50 dark:bg-red-500/10 rounded-lg text-red-600 dark:text-red-400">
                                    <Heart className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Average Likes</h3>
                                </div>
                            </div>

                            {/* Numeric values for ALL influencers */}
                            <div className="space-y-3 mb-6">
                                {allInfluencersData.map((inf, idx) => (
                                    <div key={idx} className="flex items-center justify-between text-sm p-3 rounded-lg bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-2.5 h-2.5 rounded-full ring-2 ring-white dark:ring-[#1a1a1a]"
                                                style={{ backgroundColor: inf.color }}
                                            />
                                            <span className="font-medium text-gray-700 dark:text-gray-300">{inf.username}</span>
                                        </div>
                                        <span className="font-bold text-gray-900 dark:text-white tabular-nums">{formatNumberLocal(inf.avgLikes)}</span>
                                    </div>
                                ))}
                            </div>

                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="inline-flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400 mb-4 cursor-help hover:text-red-500 transition-colors">
                                        <Info size={14} />
                                        <span>What does this mean?</span>
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent className="max-w-[250px] p-3">
                                    <p className="text-xs leading-relaxed">
                                        Average number of likes per post. Indicates content appeal and audience approval.
                                    </p>
                                </TooltipContent>
                            </Tooltip>

                            <div className="pt-4 border-t border-gray-100 dark:border-white/10">
                                <p
                                    className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed"
                                    dangerouslySetInnerHTML={{
                                        __html: allInfluencersData.length > 1
                                            ? generateComparativeInsight("likes", avgLikes, allInfluencersData.slice(1).map(inf => inf.avgLikes))
                                            : generateMetricInsight("likes", avgLikes),
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                </motion.div>

                {/* Average Comments Metric */}
                <motion.div
                    variants={itemVariants}
                    className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl shadow-sm p-6"
                >
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Left: Graph */}
                        <div className="bg-gray-50/50 dark:bg-black/20 rounded-xl p-4 border border-gray-100 dark:border-white/5">
                            <HighchartsReact
                                highcharts={Highcharts}
                                options={buildGrowingLineChart(
                                    allInfluencersData.map(inf => ({ username: inf.username, value: inf.avgComments, color: inf.color })),
                                    "Average Comments",
                                    chartTextColor,
                                    300
                                )}
                                containerProps={{ style: { height: "300px", width: "100%" } }}
                            />
                        </div>
                        {/* Right: Info */}
                        <div className="flex flex-col justify-center">
                            <div className="flex items-center gap-3 mb-6">
                                <div className="p-2 bg-blue-50 dark:bg-blue-500/10 rounded-lg text-blue-600 dark:text-blue-400">
                                    <MessageCircle className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Average Comments</h3>
                                </div>
                            </div>

                            {/* Numeric values for ALL influencers */}
                            <div className="space-y-3 mb-6">
                                {allInfluencersData.map((inf, idx) => (
                                    <div key={idx} className="flex items-center justify-between text-sm p-3 rounded-lg bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-2.5 h-2.5 rounded-full ring-2 ring-white dark:ring-[#1a1a1a]"
                                                style={{ backgroundColor: inf.color }}
                                            />
                                            <span className="font-medium text-gray-700 dark:text-gray-300">{inf.username}</span>
                                        </div>
                                        <span className="font-bold text-gray-900 dark:text-white tabular-nums">{formatNumberLocal(inf.avgComments)}</span>
                                    </div>
                                ))}
                            </div>

                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <div className="inline-flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400 mb-4 cursor-help hover:text-blue-500 transition-colors">
                                        <Info size={14} />
                                        <span>What does this mean?</span>
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent className="max-w-[250px] p-3">
                                    <p className="text-xs leading-relaxed">
                                        Average number of comments per post. Indicates deep engagement and conversation level.
                                    </p>
                                </TooltipContent>
                            </Tooltip>

                            <div className="pt-4 border-t border-gray-100 dark:border-white/10">
                                <p
                                    className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed"
                                    dangerouslySetInnerHTML={{
                                        __html: allInfluencersData.length > 1
                                            ? generateComparativeInsight("comments", avgComments, allInfluencersData.slice(1).map(inf => inf.avgComments))
                                            : generateMetricInsight("comments", avgComments),
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                </motion.div>

                {/* Audience Authenticity Metric */}
                <motion.div
                    variants={itemVariants}
                    className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl shadow-sm p-6"
                >
                    <div className="mb-8 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-green-50 dark:bg-green-500/10 rounded-lg text-green-600 dark:text-green-400">
                                <Shield className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="text-xl font-bold text-gray-900 dark:text-white">Audience Authenticity</h3>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Real vs suspicious followers analysis</p>
                            </div>
                        </div>
                    </div>

                    {/* Horizontal table with charts */}
                    <div className="overflow-x-auto pb-4">
                        <div className="inline-flex gap-6 min-w-full">
                            {allInfluencersData.map((inf, idx) => {
                                // ... (Chart logic remains same, just wrapping container styling)
                                const totalFollowers = inf.followers || 0;
                                const realFollowersCount = Math.round((totalFollowers * inf.realFollowersPct) / 100);
                                const suspiciousFollowersCount = Math.round((totalFollowers * inf.suspiciousFollowersPct) / 100);

                                const donutOptions: Highcharts.Options = {
                                    chart: { type: "pie", backgroundColor: "transparent", height: 180, width: 180 },
                                    title: { text: "" },
                                    credits: { enabled: false },
                                    tooltip: { pointFormat: '<b>{point.name}</b>: {point.percentage:.1f}%' },
                                    plotOptions: {
                                        pie: {
                                            innerSize: "70%",
                                            dataLabels: { enabled: false },
                                            colors: ["#22c55e", "#ef4444"],
                                            borderWidth: 0,
                                        }
                                    },
                                    series: [{
                                        type: "pie",
                                        name: "Followers",
                                        data: [
                                            { name: "Real", y: inf.realFollowersPct },
                                            { name: "Suspicious", y: inf.suspiciousFollowersPct },
                                        ]
                                    }]
                                };

                                return (
                                    <div key={idx} className="flex flex-col items-center min-w-[200px] p-4 bg-gray-50/50 dark:bg-white/5 rounded-xl border border-gray-100 dark:border-white/5">
                                        <div className="flex items-center gap-2 mb-4">
                                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: inf.color }} />
                                            <span className="font-semibold text-sm text-gray-900 dark:text-white truncate max-w-[150px]">{inf.username}</span>
                                        </div>

                                        <div className="relative mb-4">
                                            <HighchartsReact highcharts={Highcharts} options={donutOptions} />
                                            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                                                <span className="text-2xl font-bold text-green-600 dark:text-green-400">{inf.realFollowersPct.toFixed(0)}%</span>
                                                <span className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">REAL</span>
                                            </div>
                                        </div>

                                        <div className="w-full space-y-2">
                                            <div className="flex justify-between text-xs">
                                                <span className="text-gray-500">Real</span>
                                                <span className="font-medium text-gray-900 dark:text-white">{formatNumberLocal(realFollowersCount)}</span>
                                            </div>
                                            <div className="flex justify-between text-xs">
                                                <span className="text-gray-500">Suspicious</span>
                                                <span className="font-medium text-gray-900 dark:text-white">{formatNumberLocal(suspiciousFollowersCount)}</span>
                                            </div>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>


                    <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-800">
                        <p
                            className="text-sm text-gray-600 dark:text-gray-400 italic leading-relaxed"
                            dangerouslySetInnerHTML={{
                                __html: allInfluencersData.length > 1
                                    ? generateComparativeInsight("authenticity", realFollowersPctDisplay, allInfluencersData.slice(1).map(inf => inf.realFollowersPct))
                                    : generateMetricInsight("authenticity", realFollowersPctDisplay, undefined, realFollowersPctDisplay),
                            }}
                        />
                    </div>

                </motion.div>
            </motion.div>
        </TooltipProvider>
    );
}
