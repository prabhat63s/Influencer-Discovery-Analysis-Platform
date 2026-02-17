"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, Loader2, Lock } from "lucide-react"; // Added Lock icon
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import * as z from "zod";

import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

const formSchema = z.object({
  username: z.string().min(1, {
    message: "Username is required.",
  }),
  password: z.string().min(1, {
    message: "Password is required.",
  }),
});

interface LoginModalProps {
  children?: React.ReactNode;
  defaultOpen?: boolean;
}

export function LoginModal({ children, defaultOpen = false }: LoginModalProps) {
  const router = useRouter();
  const [open, setOpen] = useState(defaultOpen);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [showPassword, setShowPassword] = useState<boolean>(false);

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      username: "",
      password: "",
    },
  });

  async function onSubmit(values: z.infer<typeof formSchema>) {
    setIsLoading(true);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/auth/login`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            username: values.username,
            password: values.password,
          }),
        },
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Login failed");
      }

      const data = await response.json();
      const token = data.token || data.access_token || data.accessToken;

      if (token) {
        localStorage.setItem("authToken", token);
      } else {
        console.warn("No token found in response body");
        localStorage.setItem("isLoggedIn", "true");
      }

      setOpen(false);
      router.push("/dashboard");
    } catch (error) {
      console.error(error);
      form.setError("root", {
        message:
          error instanceof Error ? error.message : "Something went wrong",
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-[400px] border border-border/50 bg-background shadow-2xl p-8 sm:rounded-2xl">
        {/* Subtle Noise Texture */}
        <div className="absolute inset-0 opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')] pointer-events-none sm:rounded-2xl"></div>

        <DialogHeader className="mb-6 space-y-4">
          <div className="flex flex-col items-center gap-4">
            <div className="h-12 w-12 bg-primary/10 rounded-xl flex items-center justify-center ring-1 ring-primary/20">
              <Lock className="h-6 w-6 text-primary" />
            </div>
            <div className="space-y-1 text-center">
              <DialogTitle className="text-2xl font-bold tracking-tight">
                Welcome Back
              </DialogTitle>
              <DialogDescription className="text-center text-muted-foreground/80 font-medium">
                Enter your credentials to access your account
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="space-y-4 relative z-10"
          >
            <FormField
              control={form.control}
              name="username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-foreground font-medium">
                    Username
                  </FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Enter your username"
                      {...field}
                      className="bg-muted/30 border-input/60 focus:bg-background h-11 transition-all"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-foreground font-medium">
                    Password
                  </FormLabel>
                  <div className="relative">
                    <FormControl>
                      <Input
                        type={showPassword ? "text" : "password"}
                        placeholder="••••••••"
                        {...field}
                        className="bg-muted/30 border-input/60 focus:bg-background h-11 transition-all pr-10"
                      />
                    </FormControl>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-0 top-0 h-full px-3 text-muted-foreground hover:text-foreground hover:bg-transparent"
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                      <span className="sr-only">
                        {showPassword ? "Hide password" : "Show password"}
                      </span>
                    </Button>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />
            {form.formState.errors.root && (
              <div className="text-sm font-medium text-destructive text-center bg-destructive/10 p-2 rounded-md">
                {form.formState.errors.root.message}
              </div>
            )}
            <Button
              className="w-full h-11 text-base font-semibold shadow-lg hover:shadow-primary/25 mt-4 bg-gradient-to-r from-pink-500/95 to-purple-600/95 text-white hover:opacity-90 transition-all"
              type="submit"
              disabled={isLoading}
            >
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Sign In
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
