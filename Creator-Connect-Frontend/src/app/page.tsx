"use client"

import Image from "next/image"
import { useState, useEffect } from "react"
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Search, BarChart2, FileText, ArrowRight, Globe, ShieldCheck } from "lucide-react";
import { motion, Variants, useMotionTemplate, useMotionValue } from "framer-motion";
import UserNav from "@/components/UserNav";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Footer from "@/components/Footer";
import { RequestDemoModal } from "@/components/RequestDemoModal";
import { LoginModal } from "@/components/auth/LoginModal";
import BentoShowcase from "@/components/BentoShowcase";


export default function Home() {
    const router = useRouter()
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const [isCheckingAuth, setIsCheckingAuth] = useState(true);

    const mouseX = useMotionValue(0);
    const mouseY = useMotionValue(0);

    function handleMouseMove({ currentTarget, clientX, clientY }: React.MouseEvent) {
        const { left, top } = currentTarget.getBoundingClientRect();
        mouseX.set(clientX - left);
        mouseY.set(clientY - top);
    }

    useEffect(() => {
        const token = localStorage.getItem('authToken');
        const loggedInStatus = localStorage.getItem('isLoggedIn');
        if (token || loggedInStatus) {
            setIsLoggedIn(true);
        }
        setIsCheckingAuth(false);
    }, []);


    const container: Variants = {
        hidden: { opacity: 0 },
        show: {
            opacity: 1,
            transition: {
                staggerChildren: 0.1,
                delayChildren: 0.3,
            },
        },
    }

    const item: Variants = {
        hidden: { opacity: 0, y: 20 },
        show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 50 } },
    }

    return (
        <div className="flex flex-col min-h-screen selection:bg-primary/20 selection:text-primary relative">
            {/* Dual Spotlight Background */}
            <div className="fixed inset-0 -z-10 h-full w-full bg-background">
                <div className="absolute top-0 z-[-2] h-screen w-screen bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(168,85,247,0.25),rgba(255,255,255,0))] dark:bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(168,85,247,0.15),rgba(255,255,255,0))]"></div>
                <div className="absolute bottom-0 left-0 z-[-2] h-screen w-screen bg-[radial-gradient(ellipse_80%_80%_at_50%_120%,rgba(236,72,153,0.25),rgba(255,255,255,0))] dark:bg-[radial-gradient(ellipse_80%_80%_at_50%_120%,rgba(236,72,153,0.15),rgba(255,255,255,0))]"></div>
                <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 pointer-events-none"></div>
            </div>
            {/* Header */}
            <motion.header
                initial={{ y: -100, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.5, type: "spring", stiffness: 100, damping: 20 }}
                className="sticky top-0 z-50 w-full bg-transparent backdrop-blur-md"
            >
                <div className="container mx-auto px-4 h-16 flex items-center justify-between">
                    <div className="flex items-center font-bold md:text-xl">
                        <span className="hidden md:block">Creator Connect</span>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="hidden md:flex items-center gap-4">
                            {!isCheckingAuth && (
                                isLoggedIn ? (
                                    <Button variant="default" size="sm" onClick={() => router.push("/dashboard")}>
                                        Dashboard
                                    </Button>
                                ) : (
                                    <>
                                        <RequestDemoModal>
                                            <Button variant="secondary" size="sm" className="hidden md:flex">
                                                Book Demo
                                            </Button>
                                        </RequestDemoModal>
                                        <LoginModal>
                                            <Button variant="default" size="sm">
                                                Login
                                            </Button>
                                        </LoginModal>
                                    </>
                                )
                            )}
                        </div>
                        <ThemeToggle />
                        {isLoggedIn && <UserNav />}
                    </div>
                </div>
            </motion.header>

            {/* Hero Section */}
            <section className="relative w-full px-4 pt-24 pb-32 md:pb-48 flex flex-col items-center text-center overflow-hidden">
                <motion.div
                    variants={container}
                    initial="hidden"
                    animate="show"
                ></motion.div>

                <motion.div
                    variants={container}
                    initial="hidden"
                    animate="show"
                    className="max-w-5xl space-y-8 z-10 flex flex-col items-center"
                >
                    <motion.div variants={item} className="inline-flex items-center rounded-full border border-primary/20 bg-background/50 px-3 py-1 text-sm font-medium text-primary mb-6 backdrop-blur-md shadow-sm ring-1 ring-border/50 hover:bg-background/80 transition-colors cursor-default">
                        <span className="flex h-2 w-2 rounded-full bg-primary mr-2"></span>
                        Creator Connect v2.0
                    </motion.div>

                    {/* Floating Analytics Card - Left */}
                    <motion.div
                        initial={{ opacity: 0, x: -50 }}
                        animate={{ opacity: 1, x: 0, y: [0, -10, 0] }}
                        transition={{
                            opacity: { duration: 0.8, delay: 0.5 },
                            x: { duration: 0.8, delay: 0.5 },
                            y: { duration: 4, repeat: Infinity, ease: "easeInOut" }
                        }}
                        className="absolute left-[10%] top-[40%] hidden lg:flex items-center gap-3 p-4 rounded-2xl bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-black/5 dark:border-white/10 shadow-2xl ring-1 ring-black/5 dark:ring-white/20 select-none z-0"
                    >
                        <div className="h-10 w-10 rounded-full bg-linear-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg">
                            <BarChart2 className="text-white h-5 w-5" />
                        </div>
                        <div>
                            <p className="text-xs font-medium text-black/60 dark:text-white/60">Engagement Rate</p>
                            <p className="text-sm font-bold text-black dark:text-white flex items-center gap-1">
                                +124% <span className="text-green-500 dark:text-green-400 text-[10px]">▲</span>
                            </p>
                        </div>
                    </motion.div>

                    {/* Floating Analytics Card - Right */}
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0, y: [0, 10, 0] }}
                        transition={{
                            opacity: { duration: 0.8, delay: 0.7 },
                            x: { duration: 0.8, delay: 0.7 },
                            y: { duration: 5, repeat: Infinity, ease: "easeInOut", delay: 1 }
                        }}
                        className="absolute right-[10%] top-[30%] hidden lg:flex items-center gap-3 p-4 rounded-2xl bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-black/5 dark:border-white/10 shadow-2xl ring-1 ring-black/5 dark:ring-white/20 select-none z-0"
                    >
                        <div className="h-10 w-10 rounded-full bg-linear-to-br from-blue-500 to-cyan-500 flex items-center justify-center shadow-lg">
                            <Search className="text-white h-5 w-5" />
                        </div>
                        <div>
                            <p className="text-xs font-medium text-black/60 dark:text-white/60">Creator Discovery</p>
                            <p className="text-sm font-bold text-black dark:text-white">2.4M+ Profiles</p>
                        </div>
                    </motion.div>

                    {/* Floating Analytics Card - Bottom Left */}
                    <motion.div
                        initial={{ opacity: 0, x: -50 }}
                        animate={{ opacity: 1, x: 0, y: [0, 15, 0] }}
                        transition={{
                            opacity: { duration: 0.8, delay: 0.9 },
                            x: { duration: 0.8, delay: 0.9 },
                            y: { duration: 6, repeat: Infinity, ease: "easeInOut", delay: 0.5 }
                        }}
                        className="absolute left-[15%] top-[65%] hidden lg:flex items-center gap-3 p-4 rounded-2xl bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-black/5 dark:border-white/10 shadow-2xl ring-1 ring-black/5 dark:ring-white/20 select-none z-0"
                    >
                        <div className="h-10 w-10 rounded-full bg-linear-to-br from-emerald-500 to-green-500 flex items-center justify-center shadow-lg">
                            <Globe className="text-white h-5 w-5" />
                        </div>
                        <div>
                            <p className="text-xs font-medium text-black/60 dark:text-white/60">Total Reach</p>
                            <p className="text-sm font-bold text-black dark:text-white">850M+ Audience</p>
                        </div>
                    </motion.div>

                    {/* Floating Analytics Card - Bottom Right */}
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        animate={{ opacity: 1, x: 0, y: [0, -12, 0] }}
                        transition={{
                            opacity: { duration: 0.8, delay: 1.1 },
                            x: { duration: 0.8, delay: 1.1 },
                            y: { duration: 5.5, repeat: Infinity, ease: "easeInOut", delay: 1.5 }
                        }}
                        className="absolute right-[18%] top-[70%] hidden lg:flex items-center gap-3 p-4 rounded-2xl bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-black/5 dark:border-white/10 shadow-2xl ring-1 ring-black/5 dark:ring-white/20 select-none z-0"
                    >
                        <div className="h-10 w-10 rounded-full bg-linear-to-br from-orange-500 to-red-500 flex items-center justify-center shadow-lg">
                            <ShieldCheck className="text-white h-5 w-5" />
                        </div>
                        <div>
                            <p className="text-xs font-medium text-black/60 dark:text-white/60">Verified</p>
                            <p className="text-sm font-bold text-black dark:text-white">100% Brand Safe</p>
                        </div>
                    </motion.div>

                    <motion.h1
                        variants={item}
                        className="text-5xl md:text-8xl font-bold tracking-tight text-foreground text-balanced max-w-5xl leading-[1.05] mb-8"
                    >
                        Connect with <br className="hidden md:block" />
                        <span className="text-transparent bg-clip-text bg-linear-to-r from-pink-600 via-purple-600 to-indigo-600">Top Creators</span>
                    </motion.h1>

                    <motion.p
                        variants={item}
                        className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed font-normal"
                    >
                        Discover, analyze, and connect with top creators through <span className="text-foreground font-medium">intelligent influencer analytics</span>.
                    </motion.p>

                    <motion.div
                        variants={item}
                        className="flex items-center justify-center gap-4 pt-8 w-full flex-wrap"
                    >
                        {!isCheckingAuth && (
                            isLoggedIn ? (
                                <Button onClick={() => router.push("/dashboard")} variant="default" size="lg" className="h-12 px-10 text-base font-semibold rounded-lg shadow-lg hover:shadow-primary/25 transition-all">
                                    Go to Dashboard <ArrowRight className="h-4 w-4" />
                                </Button>
                            ) : (
                                <div className="flex items-center gap-4">
                                    <LoginModal>
                                        <Button variant="default" size="lg" className="h-12 px-10 text-base font-semibold rounded-lg shadow-lg hover:shadow-primary/25 transition-all">
                                            Get Started <ArrowRight className="h-4 w-4" />
                                        </Button>
                                    </LoginModal>
                                    <RequestDemoModal>
                                        <Button
                                            size="lg"
                                            variant="outline"
                                            className="h-12 px-8 text-base font-semibold rounded-lg border border-input bg-background hover:bg-accent hover:text-accent-foreground transition-all"
                                        >
                                            Request Demo
                                        </Button>
                                    </RequestDemoModal>
                                </div>
                            )
                        )}
                    </motion.div>
                </motion.div>
            </section>

            {/* Product Showcase Section */}
            <section className="w-full px-4 py-20 bg-background relative overflow-hidden">
                {/* Background Glow */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[600px] bg-primary/10 rounded-full blur-[120px] -z-10 pointer-events-none"></div>

                <div className="container mx-auto max-w-7xl">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        whileInView={{ opacity: 1, scale: 1 }}
                        viewport={{ once: true, margin: "-100px" }}
                        transition={{ duration: 0.8 }}
                        className="relative rounded-xl border border-white/10 shadow-2xl bg-background/50 backdrop-blur-sm overflow-hidden"
                    >
                        {/* Bento Grid Showcase */}
                        <div className="relative group">
                            <div className="absolute inset-x-0 top-0 h-11 bg-white/5 border-b border-white/10 flex items-center px-4 gap-2 z-20">
                                <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                                <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
                                <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
                            </div>
                            <div className="pt-11">
                                <BentoShowcase />
                            </div>
                        </div>
                    </motion.div>
                </div>
            </section>

            {/* Features Section */}
            <section className="px-4 py-20 bg-muted/30 border-t border-border/50">
                <div className="container mx-auto max-w-6xl">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-100px" }}
                        transition={{ duration: 0.6 }}
                        className="text-center mb-16 space-y-4"
                    >
                        <h2 className="text-3xl md:text-4xl font-bold">Intelligent Features</h2>
                        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">Everything you need to run successful influencer campaigns from start to finish.</p>
                    </motion.div>

                    <div className="grid md:grid-cols-3 gap-8">
                        {/* Feature 1 */}
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.1, duration: 0.5 }}
                            whileHover={{ y: -5 }}
                            className="group p-8 rounded-2xl bg-background/40 backdrop-blur-md border border-white/10 dark:border-white/5 hover:border-primary/50 hover:bg-background/60 transition-all shadow-sm hover:shadow-xl"
                        >
                            <div className="h-14 w-14 bg-purple-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:bg-purple-500/20 transition-colors ring-1 ring-purple-500/20">
                                <Search className="h-7 w-7 text-purple-500" />
                            </div>
                            <h3 className="text-xl font-bold mb-3">Discovery & Intelligence</h3>
                            <p className="text-muted-foreground leading-relaxed">
                                Advanced web scraping and real-time influencer discovery with AI-powered analysis and comprehensive insights.
                            </p>
                        </motion.div>

                        {/* Feature 2 */}
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.2, duration: 0.5 }}
                            whileHover={{ y: -5 }}
                            className="group p-8 rounded-2xl bg-background/40 backdrop-blur-md border border-white/10 dark:border-white/5 hover:border-purple-500/50 hover:bg-background/60 transition-all shadow-sm hover:shadow-xl"
                        >
                            <div className="h-14 w-14 bg-purple-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:bg-purple-500/20 transition-colors ring-1 ring-purple-500/20">
                                <BarChart2 className="h-7 w-7 text-purple-500" />
                            </div>
                            <h3 className="text-xl font-bold mb-3">Analytics & Verification</h3>
                            <p className="text-muted-foreground leading-relaxed">
                                Real-time performance metrics, engagement rates, audience demographics, and automated fake follower detection.
                            </p>
                        </motion.div>

                        {/* Feature 3 */}
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.3, duration: 0.5 }}
                            whileHover={{ y: -5 }}
                            className="group p-8 rounded-2xl bg-background/40 backdrop-blur-md border border-white/10 dark:border-white/5 hover:border-pink-500/50 hover:bg-background/60 transition-all shadow-sm hover:shadow-xl"
                        >
                            <div className="h-14 w-14 bg-pink-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:bg-pink-500/20 transition-colors ring-1 ring-pink-500/20">
                                <FileText className="h-7 w-7 text-pink-500" />
                            </div>
                            <h3 className="text-xl font-bold mb-3">Reporting & Strategy</h3>
                            <p className="text-muted-foreground leading-relaxed">
                                Generate detailed PDF reports with visual charts, actionable insights, and intelligent brand alignment scoring.
                            </p>
                        </motion.div>
                    </div>
                </div>
            </section>

            <div
                className="relative w-full h-[300px] md:h-[500px] px-6 bg-background overflow-hidden flex items-center justify-center group"
                onMouseMove={handleMouseMove}
            >
                <div className="absolute inset-0 bg-dot-black/[0.2] dark:bg-dot-white/[0.2] opacity-50 pointer-events-none" />

                {/* Base Text (Stroke/Dim) */}
                <h1 className="massive-text select-none text-foreground/50 dark:text-foreground font-black text-center leading-none z-0">
                    CREATOR <br /> CONNECT...
                </h1>

                {/* Spotlight Text (Glow) */}
                <motion.div
                    className="pointer-events-none absolute inset-0 flex items-center justify-center z-10"
                    style={{
                        maskImage: useMotionTemplate`radial-gradient(450px circle at ${mouseX}px ${mouseY}px, black, transparent)`,
                        WebkitMaskImage: useMotionTemplate`radial-gradient(450px circle at ${mouseX}px ${mouseY}px, black, transparent)`,
                    }}
                >
                    <h1 className="massive-text select-none font-black text-center leading-none text-transparent bg-clip-text bg-linear-to-r from-pink-600 via-purple-600 to-indigo-600 drop-shadow-2xl">
                        CREATOR <br /> CONNECT...
                    </h1>
                </motion.div>
            </div>
            <Footer />
        </div >
    );
}
