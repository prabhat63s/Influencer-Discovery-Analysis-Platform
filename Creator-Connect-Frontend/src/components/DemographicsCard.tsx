"use client"

import React from 'react'
import { motion } from 'framer-motion'
import { MapPin, Users, Activity } from 'lucide-react'

interface DemographicsCardProps {
    ageRange: string | null
    genderRatio: string | null
    geographicDistribution: string | null
    // Fallback props if passed as separate metrics
    metrics?: Record<string, unknown>
}

const DemographicsCard: React.FC<DemographicsCardProps> = ({ ageRange, genderRatio, geographicDistribution }) => {

    // Helper to parse "Male: 40%, Female: 60%" string
    const parseGender = (str: string | null) => {
        if (!str) return null;
        const maleMatch = str.match(/Male:?\s*(\d+)%/i);
        const femaleMatch = str.match(/Female:?\s*(\d+)%/i);

        const m = maleMatch ? parseInt(maleMatch[1]) : 0;
        const f = femaleMatch ? parseInt(femaleMatch[1]) : 0;

        // Normalize if needed
        if (m + f === 0) return null;
        if (m + f !== 100) { /* Optional: rescaling logic */ }

        return { male: m, female: f };
    };

    const genderData = parseGender(genderRatio);

    // Helper to parse locations "US: 40%, UK: 20%"
    const parseLocations = (str: string | null): ({ name: string; value: number } | string)[] => {
        if (!str || str.toLowerCase() === 'n/a') return [];
        // Attempt to handle both JSON array and string like "US: 40%, UK: 20%"
        try {
            if (str.startsWith('[')) {
                return JSON.parse(str).slice(0, 5);
            }
        } catch { }

        return str.split(/,|;/).map(s => {
            const [name, val] = s.split(':');
            return { name: name?.trim(), value: val ? parseFloat(val) : 0 };
        }).filter(x => x.name && !isNaN(x.value)).slice(0, 5);
    };

    const locationData = parseLocations(geographicDistribution);

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Gender Card */}
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl p-6 shadow-sm"
            >
                <div className="flex items-center gap-2 mb-6">
                    <div className="p-2 bg-blue-50 dark:bg-blue-500/10 rounded-lg text-blue-600 dark:text-blue-400">
                        <Users size={18} />
                    </div>
                    <h3 className="font-semibold text-gray-900 dark:text-white">Gender Distribution</h3>
                </div>

                {genderData ? (
                    <div className="space-y-6">
                        <div className="flex items-center justify-between text-sm font-medium">
                            <div className="flex flex-col">
                                <span className="text-2xl font-bold text-blue-600">{genderData.male}%</span>
                                <span className="text-muted-foreground">Male</span>
                            </div>
                            <div className="flex flex-col items-end">
                                <span className="text-2xl font-bold text-pink-600">{genderData.female}%</span>
                                <span className="text-muted-foreground">Female</span>
                            </div>
                        </div>
                        <div className="h-4 rounded-full bg-gray-100 dark:bg-zinc-800 overflow-hidden flex">
                            <div className="bg-blue-500 h-full" style={{ width: `${genderData.male}%` }} />
                            <div className="bg-pink-500 h-full" style={{ width: `${genderData.female}%` }} />
                        </div>
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-32 text-muted-foreground bg-gray-50 dark:bg-white/5 rounded-xl border border-dashed border-gray-200 dark:border-white/10">
                        <Users className="w-6 h-6 mb-2 opacity-50" />
                        <span className="text-sm">No gender data available</span>
                    </div>
                )}
            </motion.div>

            {/* Age Card */}
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: 0.1 }}
                className="bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl p-6 shadow-sm"
            >
                <div className="flex items-center gap-2 mb-6">
                    <div className="p-2 bg-purple-50 dark:bg-purple-500/10 rounded-lg text-purple-600 dark:text-purple-400">
                        <Activity size={18} />
                    </div>
                    <h3 className="font-semibold text-gray-900 dark:text-white">Age Range</h3>
                </div>

                {ageRange ? (
                    <div className="flex flex-col items-center justify-center h-40">
                        <span className="text-4xl font-bold text-transparent bg-clip-text bg-linear-to-r from-purple-600 to-indigo-600 dark:from-purple-400 dark:to-indigo-400">
                            {ageRange.replace(/years?|old/gi, '').trim()}
                        </span>
                        <span className="text-sm text-muted-foreground mt-2">Dominant Age Group</span>
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-40 text-muted-foreground bg-gray-50 dark:bg-white/5 rounded-xl border border-dashed border-gray-200 dark:border-white/10">
                        <Activity className="w-6 h-6 mb-2 opacity-50" />
                        <span className="text-sm">No age data available</span>
                    </div>
                )}
            </motion.div>

            {/* Locations Card (Full Width) */}
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: 0.2 }}
                className="md:col-span-2 bg-white dark:bg-white/5 border border-gray-100 dark:border-white/10 rounded-2xl p-6 shadow-sm"
            >
                <div className="flex items-center gap-2 mb-6">
                    <div className="p-2 bg-amber-50 dark:bg-amber-500/10 rounded-lg text-amber-600 dark:text-amber-400">
                        <MapPin size={18} />
                    </div>
                    <h3 className="font-semibold text-gray-900 dark:text-white">Geographic Distribution</h3>
                </div>

                {locationData.length > 0 ? (
                    <div className="space-y-4">
                        {locationData.map((loc, i) => (
                            <div key={i} className="flex items-center gap-4">
                                <span className="w-32 text-sm font-medium text-gray-700 dark:text-gray-300 truncate text-right">
                                    {typeof loc === 'string' ? loc : loc.name}
                                </span>
                                <div className="flex-1 h-3 bg-gray-100 dark:bg-zinc-800 rounded-full overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        whileInView={{ width: `${typeof loc === 'string' ? 0 : loc.value}%` }}
                                        transition={{ duration: 1, delay: i * 0.1 }}
                                        className="h-full bg-amber-500"
                                    />
                                </div>
                                <span className="w-12 text-sm text-gray-500 dark:text-gray-400 text-right">
                                    {typeof loc === 'string' ? 'N/A' : `${loc.value}%`}
                                </span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-32 text-muted-foreground bg-gray-50 dark:bg-white/5 rounded-xl border border-dashed border-gray-200 dark:border-white/10">
                        <MapPin className="w-6 h-6 mb-2 opacity-50" />
                        <span className="text-sm">No location data available</span>
                    </div>
                )}
            </motion.div>
        </div>
    )
}

export default DemographicsCard
