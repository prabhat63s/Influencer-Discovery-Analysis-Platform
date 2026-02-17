'use client'

import { motion } from 'framer-motion'
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import { User, Sparkles, TrendingUp } from 'lucide-react'

const data = [
    { name: 'Jan', value: 400 },
    { name: 'Feb', value: 300 },
    { name: 'Mar', value: 550 },
    { name: 'Apr', value: 450 },
    { name: 'May', value: 650 },
    { name: 'Jun', value: 750 },
    { name: 'Jul', value: 850 },
]

export default function BentoShowcase() {
    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full h-[500px] p-4 text-foreground">
            {/* Card 1: Live Analytics Graph (Span 2 cols) */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="md:col-span-2 row-span-2 rounded-xl bg-white/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-white/10 backdrop-blur-md overflow-hidden flex flex-col relative group shadow-sm dark:shadow-none"
            >
                <div className="p-6 border-b border-zinc-100 dark:border-white/5 flex justify-between items-center bg-white/50 dark:bg-white/5">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-purple-100 dark:bg-purple-500/20 rounded-lg">
                            <TrendingUp className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">Engagement Growth</h3>
                            <p className="text-sm text-zinc-500 dark:text-zinc-400">+124% vs last month</p>
                        </div>
                    </div>
                    <div className="px-3 py-1 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-medium border border-emerald-200 dark:border-emerald-500/20">
                        Live Data
                    </div>
                </div>
                <div className="flex-1 w-full min-h-[300px] relative p-4">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={data}>
                            <defs>
                                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#a855f7" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: 'var(--background)',
                                    borderColor: 'var(--border)',
                                    borderRadius: '8px',
                                    color: 'var(--foreground)'
                                }}
                                itemStyle={{ color: 'var(--foreground)' }}
                                cursor={{ stroke: 'var(--muted-foreground)', strokeWidth: 1 }}
                            />
                            <Line
                                type="monotone"
                                dataKey="value"
                                stroke="#a855f7"
                                strokeWidth={4}
                                dot={{ r: 4, strokeWidth: 2, fill: 'var(--background)', stroke: 'var(--border)' }}
                                activeDot={{ r: 6, stroke: '#a855f7', strokeWidth: 2, fill: '#a855f7' }}
                                animationDuration={2000}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                    {/* Floating stats */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 1, duration: 0.5 }}
                        className="absolute top-1/4 right-10 bg-white/90 dark:bg-zinc-900/90 border border-zinc-200 dark:border-white/10 p-3 rounded-xl shadow-xl backdrop-blur-md"
                    >
                        <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">Total Reach</div>
                        <div className="text-xl font-bold text-zinc-900 dark:text-white">850M+</div>
                    </motion.div>
                </div>
            </motion.div>

            {/* Card 2: Creator Profile (Top Right) */}
            <motion.div
                initial={{ opacity: 0, x: 20 }}
                whileInView={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5, delay: 0.2 }}
                className="rounded-xl bg-white/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-white/10 backdrop-blur-md p-6 flex flex-col gap-4 relative overflow-hidden group hover:border-purple-500/50 transition-colors shadow-sm dark:shadow-none"
            >
                <div className="absolute top-0 right-0 p-3">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                </div>
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-full bg-linear-to-tr from-pink-500 to-purple-600 p-[2px]">
                        <div className="w-full h-full rounded-full bg-white dark:bg-zinc-900 flex items-center justify-center overflow-hidden">
                            <User className="w-6 h-6 text-zinc-400 dark:text-white/50" />
                        </div>
                    </div>
                    <div>
                        <h4 className="font-semibold text-zinc-900 dark:text-white">Khabane Lame</h4>
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">@khaby.lame</p>
                    </div>
                </div>
                <div className="grid grid-cols-3 gap-2 py-2 border-y border-zinc-100 dark:border-white/5">
                    <div className="text-center">
                        <div className="text-xs text-zinc-500">Posts</div>
                        <div className="font-bold text-zinc-900 dark:text-white">2.4k</div>
                    </div>
                    <div className="text-center">
                        <div className="text-xs text-zinc-500">Followers</div>
                        <div className="font-bold text-zinc-900 dark:text-white">160M</div>
                    </div>
                    <div className="text-center">
                        <div className="text-xs text-zinc-500">Eng.</div>
                        <div className="font-bold text-zinc-900 dark:text-white">6.3%</div>
                    </div>
                </div>
                <div className="flex gap-2">
                    <span className="text-xs px-2 py-1 rounded-full bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300">Italy</span>
                    <span className="text-xs px-2 py-1 rounded-full bg-purple-100 dark:bg-purple-500/20 text-purple-600 dark:text-purple-300 border border-purple-200 dark:border-purple-500/20">Top 1%</span>
                </div>
            </motion.div>

            {/* Card 3: Smart Search (Bottom Right) */}
            <motion.div
                initial={{ opacity: 0, x: 20 }}
                whileInView={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5, delay: 0.4 }}
                className="rounded-xl bg-linear-to-br from-white/80 to-purple-50/50 dark:from-zinc-900/50 dark:to-purple-900/20 border border-zinc-200 dark:border-white/10 backdrop-blur-md p-6 flex flex-col justify-center gap-4 relative overflow-hidden shadow-sm dark:shadow-none"
            >
                <div className="absolute inset-0 bg-purple-500/5 opacity-0 hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

                <div className="space-y-2">
                    <h4 className="text-sm font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">AI Discovery</h4>
                    <div className="relative group">
                        <div className="absolute inset-0 bg-pink-500/20 blur-xl rounded-full opacity-0 group-hover:opacity-50 transition-opacity" />
                        <div className="relative bg-white dark:bg-black/40 border border-zinc-200 dark:border-white/10 rounded-full h-10 flex items-center px-4 gap-3 text-sm text-zinc-600 dark:text-zinc-300 shadow-sm dark:shadow-none">
                            <Sparkles className="w-4 h-4 text-pink-500 animate-pulse" />
                            <span>Find tech influencers in...</span>
                        </div>
                        {/* Floating cursor animation could go here */}
                        <motion.div
                            animate={{ x: [0, 10, 0], y: [0, 5, 0] }}
                            transition={{ duration: 4, repeat: Infinity }}
                            className="absolute -bottom-6 -right-2 bg-white dark:bg-zinc-800 text-xs px-2 py-1 rounded-md border border-zinc-200 dark:border-white/10 shadow-lg text-zinc-600 dark:text-zinc-300 pointer-events-none"
                        >
                            Searching...
                        </motion.div>
                    </div>
                </div>

                <div className="flex flex-wrap gap-2 mt-2">
                    {['Tech', 'US', '>1M'].map((tag, i) => (
                        <motion.div
                            key={tag}
                            initial={{ opacity: 0, scale: 0 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 1 + (i * 0.2) }}
                            className="px-2 py-1 rounded-md bg-white dark:bg-white/5 border border-zinc-200 dark:border-white/10 text-xs text-zinc-500 dark:text-zinc-400 shadow-sm dark:shadow-none"
                        >
                            {tag}
                        </motion.div>
                    ))}
                </div>
            </motion.div>
        </div>
    )
}
