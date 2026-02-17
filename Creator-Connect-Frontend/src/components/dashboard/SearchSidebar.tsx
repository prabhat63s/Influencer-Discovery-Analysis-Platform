import { useRouter } from "next/navigation";
import { AnimatePresence, motion, Variants } from "framer-motion";
import { SendHorizonal } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { NICHE_OPTIONS } from "@/constants/niche.constants";

interface SearchSidebarProps {
    resultLimit: string;
    setResultLimit: (value: string) => void;
    niche: string;
    setNiche: (value: string) => void;
    location: string;
    setLocation: (value: string) => void;
    minFollowers: string;
    setMinFollowers: (value: string) => void;
    maxFollowers: string;
    setMaxFollowers: (value: string) => void;
    promptText: string;
    setPromptText: (value: string) => void;
    handleAskAI: () => void;
    isLoading: boolean;
    error: string | null;
    itemVariants: Variants;
}

export const SearchSidebar = ({
    resultLimit,
    setResultLimit,
    niche,
    setNiche,
    location,
    setLocation,
    minFollowers,
    setMinFollowers,
    maxFollowers,
    setMaxFollowers,
    promptText,
    setPromptText,
    handleAskAI,
    isLoading,
    error,
    itemVariants,
}: SearchSidebarProps) => {
    const router = useRouter();

    return (
        <motion.div className="w-full" variants={itemVariants}>
            {/* Logo */}
            <div
                className="flex items-center px-4 shrink-0 cursor-pointer"
                onClick={() => router.push("/")}
            >
                <AnimatePresence>
                    <motion.span
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -10 }}
                        transition={{ duration: 0.2 }}
                        className="font-extrabold text-lg whitespace-nowrap"
                    >
                        Creator Connect
                    </motion.span>
                </AnimatePresence>
            </div>
            {/* Tab */}
            <div className="p-6">
                <h1 className="text-lg font-bold pb-2">Search</h1>
                <div className="space-y-2">
                    {/* Result Limit */}
                    <div className="space-y-2">
                        <Label className="text-xs font-medium">Result Limit (optional)</Label>
                        <input
                            type="number"
                            min="50"
                            value={resultLimit}
                            onChange={(e) => setResultLimit(e.target.value)}
                            placeholder="e.g. 60"
                            className="w-full focus:outline-none rounded-lg px-3 py-2 text-sm border bg-secondary/50 focus:ring-2 ring-primary/20 transition-all font-medium placeholder:text-muted-foreground/50"
                        />
                    </div>
                    {/* Niche */}
                    <div className="space-y-2">
                        <Label className="text-xs font-medium">Niche</Label>
                        <Select value={niche} onValueChange={setNiche}>
                            <SelectTrigger className="w-full">
                                <SelectValue placeholder="Select Niche" />
                            </SelectTrigger>
                            <SelectContent>
                                {NICHE_OPTIONS.map((nicheOption) => (
                                    <SelectItem key={nicheOption} value={nicheOption} className="text-xs">
                                        {nicheOption}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    {/* Location */}
                    <div className="space-y-2">
                        <Label className="text-xs font-medium">Location</Label>
                        <input
                            type="text"
                            value={location}
                            onChange={(e) => setLocation(e.target.value)}
                            placeholder="e.g. India"
                            className="w-full focus:outline-none rounded-lg px-3 py-2 text-sm border bg-secondary/50 focus:ring-2 ring-primary/20 transition-all font-medium placeholder:text-muted-foreground/50"
                        />
                    </div>
                    {/* Followers */}
                    <div className="space-y-2">
                        <Label className="text-xs font-medium">Followers Range</Label>
                        <div className="grid grid-cols-2 gap-2">
                            <div className="space-y-1">
                                <label className="text-xs text-muted-foreground">Min</label>
                                <input
                                    type="text"
                                    value={minFollowers}
                                    onChange={(e) => setMinFollowers(e.target.value)}
                                    placeholder="e.g. 100K"
                                    className="w-full focus:outline-none rounded-lg px-3 py-2 text-sm border bg-secondary/50 focus:ring-2 ring-primary/20 transition-all font-medium placeholder:text-muted-foreground/50"
                                />
                            </div>
                            <div className="space-y-1">
                                <label className="text-xs text-muted-foreground">Max</label>
                                <input
                                    type="text"
                                    value={maxFollowers}
                                    onChange={(e) => setMaxFollowers(e.target.value)}
                                    placeholder="e.g. 1M"
                                    className="w-full focus:outline-none rounded-lg px-3 py-2 text-sm border bg-secondary/50 focus:ring-2 ring-primary/20 transition-all font-medium placeholder:text-muted-foreground/50"
                                />
                            </div>
                        </div>
                    </div>
                    <div className="w-full mt-6 bg-background rounded-md">
                        <textarea
                            name="prompt"
                            id="prompt"
                            placeholder="Enter your prompt"
                            value={promptText}
                            onChange={(e) => setPromptText(e.target.value)}
                            className="w-full text-sm focus:outline-none rounded-lg p-3 resize-none hide-scrollbar bg-secondary/50 border focus:ring-2 ring-primary/20 transition-all"
                            rows={8}
                        ></textarea>
                    </div>
                    {error && (
                        <div className="text-xs text-red-500 mt-2">
                            {error}
                        </div>
                    )}
                    <Button
                        className="w-full flex items-center gap-2 bg-gradient-to-r from-pink-500/95 to-purple-600/95 text-white hover:opacity-90 transition-all font-medium"
                        size="sm"
                        variant="default"
                        onClick={handleAskAI}
                        disabled={isLoading}
                    >
                        <SendHorizonal /> {isLoading ? "Searching..." : "Ask AI"}
                    </Button>
                </div>
            </div>
        </motion.div>
    );
};
