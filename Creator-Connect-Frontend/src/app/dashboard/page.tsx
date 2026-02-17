"use client";

import { motion, Variants } from "framer-motion";
import ProfileSidebar from "@/components/dashboard/ProfileSidebar";
import CreatorResults from "@/components/dashboard/CreatorResults";
import { CreatorProfile } from "@/types/creator.types";
import { MOCK_CREATORS } from "@/constants/mockData.constants";
import { useCreatorSearch } from "@/hooks/useCreatorSearch";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { SearchSidebar } from "@/components/dashboard/SearchSidebar";
import { Sheet, SheetContent, SheetTrigger, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Filter } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useMemo, useState } from "react";

const DashboardPage = () => {
  const {
    selectedCreator,
    setSelectedCreator,
    promptText,
    setPromptText,
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
    isLoading,
    error,
    searchResults,
    hasSearched,
    handleAskAI,
    conversationId
  } = useCreatorSearch();

  // Client-side Filter States
  const [filterNiche] = useState("Any");
  const [filterEngagement, setFilterEngagement] = useState("0");
  const [filterMinFollowers, setFilterMinFollowers] = useState("");
  const [filterMaxFollowers, setFilterMaxFollowers] = useState("");
  const [filterLocation, setFilterLocation] = useState("");

  // Helpers
  const parseFollowers = (val: string | number): number => {
    if (typeof val === 'number') return val;
    if (!val) return 0;
    const str = String(val).toUpperCase().replace(/,/g, '');
    const num = parseFloat(str);
    if (isNaN(num)) return 0;
    if (str.includes('K')) return num * 1000;
    if (str.includes('M')) return num * 1000000;
    if (str.includes('B')) return num * 1000000000;
    return num;
  };

  const parseEngagement = (val: string | number): number => {
    if (typeof val === 'number') return val;
    if (!val) return 0;
    return parseFloat(String(val).replace('%', ''));
  };

  // Filter Logic - derived state via useMemo to avoid setState in effect
  const filteredCreators = useMemo(() => {
    const results = hasSearched ? searchResults : MOCK_CREATORS;

    return results.filter((creator: CreatorProfile) => {
      // Niche
      if (filterNiche !== "Any") {
        const creatorNiche = (creator.niche || creator.NICHE || "").toLowerCase();
        if (!creatorNiche.includes(filterNiche.toLowerCase())) return false;
      }

      // Location
      if (filterLocation) {
        const creatorLoc = (creator.location || creator.LOCATION || "").toLowerCase();
        if (!creatorLoc.includes(filterLocation.toLowerCase())) return false;
      }

      // Engagement (coerce to string|number; metrics values are unknown from Record)
      const engVal = creator.stats?.engagement ?? creator.engagement_rate ?? creator.metrics?.engagement_rate ?? "0";
      const creatorEng = parseEngagement(typeof engVal === "string" || typeof engVal === "number" ? engVal : String(engVal));
      if (creatorEng < parseFloat(filterEngagement)) return false;

      // Followers
      const follVal = creator.stats?.followers ?? creator.followers ?? creator.metrics?.followers ?? "0";
      const creatorFoll = parseFollowers(typeof follVal === "string" || typeof follVal === "number" ? follVal : String(follVal));
      if (filterMinFollowers) {
        const min = parseFollowers(filterMinFollowers);
        if (creatorFoll < min) return false;
      }
      if (filterMaxFollowers) {
        const max = parseFollowers(filterMaxFollowers);
        if (creatorFoll > max) return false;
      }

      return true;
    });
  }, [searchResults, hasSearched, filterNiche, filterEngagement, filterMinFollowers, filterMaxFollowers, filterLocation]);


  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  };

  const itemVariants: Variants = {
    hidden: { y: 20, opacity: 0 },
    visible: {
      y: 0,
      opacity: 1,
      transition: {
        type: "spring",
        stiffness: 100,
      },
    },
  };

  return (
    <motion.div
      className="flex h-screen overflow-hidden bg-gradient-to-br from-white/90 via-white/50 to-pink-50/30 dark:from-black/90 dark:via-black/40 dark:to-purple-900/20 relative backdrop-blur-sm"
      initial="visible"
      animate="visible"
      variants={containerVariants}
    >
      <div className="hidden md:block w-1/5 border-r h-full bg-gray-50/40 dark:bg-neutral-950">
        <SearchSidebar
          resultLimit={resultLimit}
          setResultLimit={setResultLimit}
          niche={niche}
          setNiche={setNiche}
          location={location}
          setLocation={setLocation}
          minFollowers={minFollowers}
          setMinFollowers={setMinFollowers}
          maxFollowers={maxFollowers}
          setMaxFollowers={setMaxFollowers}
          promptText={promptText}
          setPromptText={setPromptText}
          handleAskAI={handleAskAI}
          isLoading={isLoading}
          error={error}
          itemVariants={itemVariants}
        />
      </div>

      {/* Main Content */}
      <motion.div
        className="w-full md:w-4/5 relative backdrop-blur-sm"
        variants={itemVariants}
      >
        <DashboardHeader />
        <div className="h-[calc(100vh-54px)] overflow-y-auto p-4 md:p-6 bg-transparent scroll-smooth">
          <div className="mb-8 flex flex-col gap-1">
            <div className="flex flex-col gap-4">
              {/* Filters Header */}
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Refine Results</h3>
                {/* Mobile Filter Button (for Search Sidebar) */}
                <div className="md:hidden">
                  <Sheet>
                    <SheetTrigger asChild>
                      <Button variant="outline" size="sm" className="gap-2">
                        <Filter className="h-4 w-4" /> Ask AI
                      </Button>
                    </SheetTrigger>
                    <SheetContent side="left" className="p-0 w-[320px] sm:w-[540px]">
                      <SheetHeader className="sr-only">
                        <SheetTitle>Filters</SheetTitle>
                      </SheetHeader>
                      <SearchSidebar
                        resultLimit={resultLimit}
                        setResultLimit={setResultLimit}
                        niche={niche}
                        setNiche={setNiche}
                        location={location}
                        setLocation={setLocation}
                        minFollowers={minFollowers}
                        setMinFollowers={setMinFollowers}
                        maxFollowers={maxFollowers}
                        setMaxFollowers={setMaxFollowers}
                        promptText={promptText}
                        setPromptText={setPromptText}
                        handleAskAI={handleAskAI}
                        isLoading={isLoading}
                        error={error}
                        itemVariants={itemVariants}
                      />
                    </SheetContent>
                  </Sheet>
                </div>
              </div>

              {/* Filters Content - Grid Layout */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-4 bg-white/50 dark:bg-black/20 rounded-xl border shadow-sm backdrop-blur-md">

                {/* Niche Filter */}
                {/* <div className="space-y-2">
                  <Label className="text-xs font-medium">Niche</Label>
                  <Select value={filterNiche} onValueChange={setFilterNiche}>
                    <SelectTrigger className="w-full bg-white/80 dark:bg-black/50">
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
                </div> */}

                {/* Engagement Filter */}
                <div className="space-y-2">
                  <Label className="text-xs font-medium">Engagement Rate</Label>
                  <Select value={filterEngagement} onValueChange={setFilterEngagement}>
                    <SelectTrigger className="w-full bg-white/80 dark:bg-black/50">
                      <SelectValue placeholder="Min Engagement" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0" className="text-xs">Any</SelectItem>
                      <SelectItem value="0.5" className="text-xs">≥0.5%</SelectItem>
                      <SelectItem value="1" className="text-xs">≥1%</SelectItem>
                      <SelectItem value="2" className="text-xs">≥2%</SelectItem>
                      <SelectItem value="3" className="text-xs">≥3%</SelectItem>
                      <SelectItem value="4" className="text-xs">≥4%</SelectItem>
                      <SelectItem value="5" className="text-xs">≥5%</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Followers Filter */}
                <div className="space-y-2">
                  <Label className="text-xs font-medium">Followers Range</Label>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <input
                        type="text"
                        placeholder="Min (e.g 10K)"
                        value={filterMinFollowers}
                        onChange={(e) => setFilterMinFollowers(e.target.value)}
                        className="w-full focus:outline-none rounded-md px-2 py-2 text-xs border bg-white/80 dark:bg-black/50"
                      />
                    </div>
                    <div className="space-y-1">
                      <input
                        type="text"
                        placeholder="Max (e.g 1M)"
                        value={filterMaxFollowers}
                        onChange={(e) => setFilterMaxFollowers(e.target.value)}
                        className="w-full focus:outline-none rounded-md px-2 py-2 text-xs border bg-white/80 dark:bg-black/50"
                      />
                    </div>
                  </div>
                </div>

                {/* Location Filter */}
                <div className="space-y-2">
                  <Label className="text-xs font-medium">Location</Label>
                  <input
                    type="text"
                    placeholder="Filter by location..."
                    value={filterLocation}
                    onChange={(e) => setFilterLocation(e.target.value)}
                    className="w-full focus:outline-none rounded-md px-2 py-2 text-xs border bg-white/80 dark:bg-black/50"
                  />
                </div>

              </div>
            </div>
          </div>

          <CreatorResults
            onViewProfile={setSelectedCreator}
            creators={filteredCreators}
            isLoading={isLoading}
          />
        </div>
      </motion.div>

      <ProfileSidebar
        isOpen={!!selectedCreator}
        onOpenChange={(open) => !open && setSelectedCreator(null)}
        creator={selectedCreator}
        conversationId={conversationId}
      />
    </motion.div>
  );
};

export default DashboardPage;
