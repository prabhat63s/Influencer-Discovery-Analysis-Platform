import { LayoutDashboard } from "lucide-react";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import UserNav from "@/components/UserNav";

export const DashboardHeader = () => {
    return (
        <header className="border-b flex px-6 py-4 md:py-2 bg-transparent items-center justify-between">
            <h1 className="text-lg font-bold flex items-center gap-2">
                <div className="p-1.5 rounded-md bg-purple-100 dark:bg-purple-900/20">
                    <LayoutDashboard size={18} className="text-purple-600/95" />
                </div>
                Dashboard
            </h1>
            <div className="flex items-center gap-4">
                <ThemeToggle />
                <UserNav />
            </div>
        </header>
    );
};
