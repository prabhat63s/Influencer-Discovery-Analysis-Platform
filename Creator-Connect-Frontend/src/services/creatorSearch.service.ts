import { CreatorProfile } from "@/types/creator.types";

export interface SearchFilters {
    niche?: string;
    location?: string;
    minFollowers?: string;
    maxFollowers?: string;
}

export interface SearchParams {
    query: string;
    filters: SearchFilters;
}

export interface SearchResponse {
    complete?: boolean;
    message?: string;
    next_question?: string;
    search_results?: CreatorProfile[];
    results?: CreatorProfile[];
    final_prompt?: string;
    conversation_id?: string;
}

export interface SearchResult {
    results: CreatorProfile[];
    query: string;
    timestamp: string;
    filters: {
        niche: string | null;
        location: string | null;
        followersRange: string | null;
    };
}

/**
 * Builds a followers range string from min and max values
 */
export const buildFollowersRange = (minFollowers?: string, maxFollowers?: string): string => {
    if (minFollowers && maxFollowers) {
        return `${minFollowers}-${maxFollowers}`;
    } else if (minFollowers) {
        return `${minFollowers}+`;
    } else if (maxFollowers) {
        return `0-${maxFollowers}`;
    }
    return "";
};

/**
 * Calls the dynamic search API with the provided query and filters
 */
export const searchCreators = async (params: SearchParams): Promise<SearchResponse> => {
    const { query, filters } = params;
    const followersRange = buildFollowersRange(filters.minFollowers, filters.maxFollowers);

    // Create FormData
    const formData = new FormData();
    formData.append("query", query);
    formData.append("conversation_id", `dashboard-${Date.now()}`);

    if (filters.niche && filters.niche !== "Any") {
        formData.append("niche", filters.niche);
    }
    if (filters.location) {
        formData.append("location", filters.location);
    }
    if (followersRange) {
        formData.append("followers_range", followersRange);
    }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    const response = await fetch(`${apiUrl}/api/dynamic-search/prompt`, {
        method: "POST",
        body: formData,
    });

    if (!response.ok) {
        throw new Error(`API request failed with status ${response.status}`);
    }

    return response.json();
};

/**
 * Normalizes the API response to extract search results
 */
export const normalizeSearchResults = (data: SearchResponse): CreatorProfile[] => {
    return Array.isArray(data?.search_results)
        ? data.search_results
        : Array.isArray(data?.results)
            ? data.results
            : [];
};

/**
 * Saves search results to localStorage
 */
export const saveSearchToLocalStorage = (searchResult: SearchResult): void => {
    try {
        localStorage.setItem('dashboard_search_results', JSON.stringify(searchResult));
    } catch (error) {
        console.error('Error saving search results to localStorage:', error);
    }
};

/**
 * Loads search results from localStorage
 */
export const loadSearchFromLocalStorage = (): SearchResult | null => {
    try {
        const savedSearch = localStorage.getItem('dashboard_search_results');
        if (savedSearch) {
            return JSON.parse(savedSearch);
        }
    } catch (error) {
        console.error('Error loading search results from localStorage:', error);
    }
    return null;
};
