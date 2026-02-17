"use client"

import { useState } from "react"
import { useForm, UseFormReturn } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { Loader2, CheckCircle2, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { AnimatePresence, motion } from "framer-motion"
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form"
import {
    Dialog,
    DialogContent,
    DialogTrigger,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog"
import { requestDemo } from "@/services/contact.service"
import { toast } from "sonner"

const formSchema = z.object({
    name: z.string().min(2, {
        message: "Name must be at least 2 characters.",
    }),
    email: z.string().email({
        message: "Please enter a valid email address.",
    }),
})

type FormValues = z.infer<typeof formSchema>

interface RequestDemoModalProps {
    children?: React.ReactNode
}

export function RequestDemoModal({ children }: RequestDemoModalProps) {
    const [open, setOpen] = useState(false)
    const [isLoading, setIsLoading] = useState(false)
    const [isSuccess, setIsSuccess] = useState(false)

    const form = useForm<FormValues>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            name: "",
            email: "",
        },
    })

    async function onSubmit(values: FormValues) {
        setIsLoading(true)
        try {
            await requestDemo(values)
            setIsLoading(false)
            setIsSuccess(true)

            // Reset after showing success
            setTimeout(() => {
                setOpen(false)
                setIsSuccess(false)
                form.reset()
            }, 3000)
        } catch (error) {
            setIsLoading(false)
            console.error("Failed to request demo:", error)
            toast.error("Failed to send request. Please try again later.")
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                {children}
            </DialogTrigger>
            <DialogContent className="max-w-7xl w-[90%] border bg-transparent shadow-2xl p-0 overflow-hidden sm:rounded-3xl">
                <DialogTitle className="sr-only">Request a Demo</DialogTitle>
                <DialogDescription className="sr-only">
                    Fill out the form to request a demo of Creator Connect.
                </DialogDescription>
                <div className="w-full bg-background/95 backdrop-blur-xl p-8 md:p-12 flex flex-col justify-center relative">
                    <AnimatePresence mode="wait">
                        {!isSuccess ? (
                            <DemoForm
                                form={form}
                                isLoading={isLoading}
                                onSubmit={onSubmit}
                            />
                        ) : (
                            <SuccessView onClose={() => setOpen(false)} />
                        )}
                    </AnimatePresence>
                </div>
            </DialogContent>
        </Dialog>
    )
}

interface DemoFormProps {
    form: UseFormReturn<FormValues>
    isLoading: boolean
    onSubmit: (values: FormValues) => void
}

function DemoForm({ form, isLoading, onSubmit }: DemoFormProps) {
    return (
        <motion.div
            key="form"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
            className="max-w-md mx-auto w-full"
        >
            <div className="mb-8 space-y-2">
                <h3 className="text-2xl font-bold tracking-tight text-foreground">Book a Demo</h3>
                <p className="text-muted-foreground text-sm">
                    Fill out the form below and our team will get back to you within 24 hours.
                </p>
            </div>

            <Form {...form}>
                <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
                    <FormField
                        control={form.control}
                        name="name"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel className="text-foreground/80 font-medium">Full Name</FormLabel>
                                <FormControl>
                                    <Input
                                        placeholder="Jane Doe"
                                        {...field}
                                        className="bg-muted/50 border-input/50 focus:bg-background focus:border-primary/50 focus:ring-4 focus:ring-primary/10 h-11 transition-all rounded-lg"
                                    />
                                </FormControl>
                                <FormMessage />
                            </FormItem>
                        )}
                    />
                    <FormField
                        control={form.control}
                        name="email"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel className="text-foreground/80 font-medium">Work Email</FormLabel>
                                <FormControl>
                                    <Input
                                        placeholder="jane@company.com"
                                        {...field}
                                        className="bg-muted/50 border-input/50 focus:bg-background focus:border-primary/50 focus:ring-4 focus:ring-primary/10 h-11 transition-all rounded-lg"
                                    />
                                </FormControl>
                                <FormMessage />
                            </FormItem>
                        )}
                    />
                    <div className="pt-2">
                        <Button
                            className="w-full h-12 text-base font-semibold shadow-lg shadow-purple-500/20 hover:shadow-purple-500/30 transition-all rounded-lg bg-linear-to-r from-pink-500/95 to-purple-600/95 text-white hover:opacity-90"
                            size="lg"
                            type="submit"
                            disabled={isLoading}
                        >
                            {isLoading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Sending Request...
                                </>
                            ) : (
                                <>
                                    Request Demo <ArrowRight className="ml-2 h-4 w-4" />
                                </>
                            )}
                        </Button>
                    </div>
                </form>
            </Form>
        </motion.div>
    )
}

function SuccessView({ onClose }: { onClose: () => void }) {
    return (
        <motion.div
            key="success"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.4, type: "spring", stiffness: 100 }}
            className="flex flex-col items-center justify-center h-full w-full text-center space-y-6"
        >
            <div className="relative">
                <div className="absolute inset-0 bg-green-500/20 rounded-full blur-xl animate-pulse"></div>
                <div className="w-24 h-24 bg-linear-to-br from-green-400 to-emerald-600 rounded-full flex items-center justify-center shadow-2xl relative z-10">
                    <CheckCircle2 className="w-10 h-10 text-white" />
                </div>
            </div>

            <div className="space-y-2 max-w-[300px]">
                <h3 className="text-3xl font-bold tracking-tight text-foreground">You&apos;re all set!</h3>
                <p className="text-muted-foreground text-base leading-relaxed">
                    Thanks for your interest. We&apos;ve received your request and will be in touch shortly.
                </p>
            </div>

            <Button
                variant="outline"
                className="mt-4 border-input bg-background/50 hover:bg-muted transition-colors rounded-full px-8"
                onClick={onClose}
            >
                Close
            </Button>
        </motion.div>
    )
}
