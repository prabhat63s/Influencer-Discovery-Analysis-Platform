"use client"

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Bot, X, Send, Sparkles, User, Loader2, BarChart3, Wallet, History, Zap, Info, TrendingUp, Gem, List, Mic, ArrowRight, Terminal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import ReactMarkdown from 'react-markdown'
import { useVoiceTyping } from '@/hooks/useVoiceTyping'
import remarkGfm from 'remark-gfm'

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

const Chatbot = () => {
    const [isOpen, setIsOpen] = useState(false)
    const [isVisible, setIsVisible] = useState(false)
    const [messages, setMessages] = useState<Message[]>([
        { role: 'assistant', content: 'Hi there! I can help you find the perfect creators for your campaign. What represent you looking for?' }
    ])
    const [input, setInput] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLTextAreaElement>(null)

    const { isListening, toggleListening } = useVoiceTyping((transcript) => {
        setInput(prev => prev + (prev ? ' ' : '') + transcript)
    })


    const quickActions = [
        { label: 'Usage', text: 'Show my usage statistics', icon: BarChart3, color: 'text-purple-400 group-hover:text-purple-300' },
        { label: 'Costs', text: 'Show my cost breakdown', icon: Wallet, color: 'text-emerald-400 group-hover:text-emerald-300' },
        { label: 'History', text: 'Show my search history', icon: History, color: 'text-blue-400 group-hover:text-blue-300' },
        { label: 'Quota', text: 'How many searches do I have left?', icon: Zap, color: 'text-yellow-400 group-hover:text-yellow-300' },
    ]

    const apiUrl = process.env.NEXT_PUBLIC_API_URL;

    useEffect(() => {
        const token = localStorage.getItem('authToken')
        const loggedInStatus = localStorage.getItem('isLoggedIn')
        if (token || loggedInStatus) {
            setIsVisible(true)
        }
    }, [])

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    useEffect(() => {
        if (isOpen && inputRef.current) {
            // setTimeout to ensure the element is focusable after animation starts
            setTimeout(() => {
                inputRef.current?.focus()
            }, 300)
        }
    }, [isOpen])

    const toggleChat = () => setIsOpen(!isOpen)

    const sendMessage = async (e?: React.FormEvent, overrideText?: string) => {
        e?.preventDefault()
        const textToSend = overrideText || input
        if (!textToSend.trim() || isLoading) return

        const userMessage: Message = { role: 'user', content: textToSend }
        setMessages(prev => [...prev, userMessage])
        setInput('')
        setIsLoading(true)

        try {
            const response = await fetch(`${apiUrl}/api/agent/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    messages: [...messages, userMessage].map(m => ({
                        role: m.role,
                        content: m.content
                    }))
                }),
            })

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`)
            }

            const data = await response.json()
            const assistantMessage: Message = {
                role: 'assistant',
                content: data.message
            }
            setMessages(prev => [...prev, assistantMessage])
        } catch (error) {
            console.error('Error sending message:', error)
            const errorMessage: Message = {
                role: 'assistant',
                content: 'Sorry, I encountered an error. Please make sure the backend is running and try again.'
            }
            setMessages(prev => [...prev, errorMessage])
        } finally {
            setIsLoading(false)
        }
    }

    const handleQuickAction = (text: string) => {
        sendMessage(undefined, text)
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            sendMessage()
        }
    }

    if (!isVisible) return null

    return (
        <div className='fixed bottom-8 right-8 z-50 flex flex-col items-end gap-4'>
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, y: 20, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 20, scale: 0.95 }}
                        transition={{ duration: 0.2 }}
                        className="fixed inset-0 md:static z-50 w-full h-full md:w-[380px] md:h-[550px] bg-background/80 backdrop-blur-xl border border-white/10 md:rounded-2xl shadow-2xl flex flex-col overflow-hidden ring-black/5 dark:ring-white/10"
                    >
                        {/* Header */}
                        <div className="p-4 border-b border-white/10 bg-white/5 flex items-center justify-between shrink-0">
                            <div className="flex items-center gap-2">
                                <div className="h-8 w-8 rounded-full bg-linear-to-br from-pink-500 to-purple-600 flex items-center justify-center shadow-sm">
                                    <Bot className="h-4 w-4 text-white" />
                                </div>
                                <div>
                                    <h3 className="font-semibold text-sm">Creator AI</h3>
                                    <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                                        <span className={`w-1.5 h-1.5 rounded-full ${isLoading ? 'bg-yellow-500' : 'bg-green-500'} animate-pulse`} />
                                        {isLoading ? 'Thinking...' : 'Online'}
                                    </p>
                                </div>
                            </div>
                            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full hover:bg-white/10" onClick={toggleChat}>
                                <X className="h-4 w-4" />
                            </Button>
                        </div>

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth">
                            {messages.map((msg, idx) => (
                                <div
                                    key={idx}
                                    className={`flex items-start gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                                >
                                    <div className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'assistant' ? 'bg-linear-to-br from-pink-500 to-purple-600' : 'bg-secondary'}`}>
                                        {msg.role === 'assistant' ? <Bot className="h-4 w-4 text-white" /> : <User className="h-4 w-4" />}
                                    </div>
                                    <div
                                        className={`rounded-2xl p-3 text-sm max-w-[85%] ${msg.role === 'user'
                                            ? 'bg-primary text-primary-foreground rounded-tr-sm'
                                            : 'bg-muted/50 border rounded-tl-sm prose prose-invert prose-sm max-w-none'
                                            }`}
                                    >
                                        {msg.role === 'assistant' ? (
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                components={{
                                                    h1: ({ children }) => (
                                                        <h1 className="text-2xl font-bold mb-4 mt-6 flex items-center gap-3 pb-2 border-b">
                                                            <span className="h-1.5 w-1.5 rounded-full bg-purple-500 shadow-[0_0_10px_rgba(168,85,247,0.5)]" />
                                                            {children}
                                                        </h1>
                                                    ),
                                                    h2: ({ children }) => {
                                                        const text = String(children).toLowerCase()
                                                        let icon = <Info className="w-4 h-4 text-cyan-400" />
                                                        let style = "border-cyan-500/20 bg-cyan-500/10 text-cyan-200"

                                                        if (text.includes('market')) {
                                                            icon = <TrendingUp className="w-4 h-4 text-purple-400" />
                                                            style = "border-purple-500/20 bg-purple-500/10 text-purple-200"
                                                        }
                                                        if (text.includes('product')) {
                                                            icon = <Gem className="w-4 h-4 text-pink-400" />
                                                            style = "border-pink-500/20 bg-pink-500/10 text-pink-200"
                                                        }
                                                        if (text.includes('value')) {
                                                            icon = <BarChart3 className="w-4 h-4 text-green-400" />
                                                            style = "border-green-500/20 bg-green-500/10 text-green-200"
                                                        }
                                                        if (text.includes('business')) {
                                                            icon = <List className="w-4 h-4 text-yellow-400" />
                                                            style = "border-yellow-500/20 bg-yellow-500/10 text-yellow-200"
                                                        }

                                                        return (
                                                            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border w-fit mb-4 mt-6 ${style}`}>
                                                                {icon}
                                                                <h2 className="text-sm font-semibold tracking-wide uppercase">{children}</h2>
                                                            </div>
                                                        )
                                                    },
                                                    h3: ({ children }) => (
                                                        <h3 className="text-base font-semibold mt-4 mb-2 flex items-center gap-2">
                                                            <ArrowRight className="w-3.5 h-3.5" />
                                                            {children}
                                                        </h3>
                                                    ),
                                                    p: ({ children }) => (
                                                        <p className="leading-6 text-sm">
                                                            {children}
                                                        </p>
                                                    ),
                                                    ul: ({ children }) => (
                                                        <ul className="flex flex-col gap-2 my-4 pl-1">
                                                            {children}
                                                        </ul>
                                                    ),
                                                    ol: ({ children }) => (
                                                        <ol className="flex flex-col gap-2 my-4 list-decimal pl-5 text-sm">
                                                            {children}
                                                        </ol>
                                                    ),
                                                    li: ({ children }) => (
                                                        <li className="flex items-start gap-2.5 text-sm">
                                                            <div className="mt-2 h-1.5 w-1.5 rounded-full bg-neutral-600 shrink-0" />
                                                            <span className="flex-1">{children}</span>
                                                        </li>
                                                    ),
                                                    a: ({ href, children }) => (
                                                        <a
                                                            href={href}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-purple-400 hover:text-purple-300 underline underline-offset-4 decoration-purple-500/30 hover:decoration-purple-500 transition-colors"
                                                        >
                                                            {children}
                                                        </a>
                                                    ),
                                                    code: ({ className, children, ...props }) => {
                                                        const match = /language-(\w+)/.exec(className || '')
                                                        const isInline = !match

                                                        if (isInline) {
                                                            return (
                                                                <code className="px-1.5 py-0.5 rounded-md bg-white/10 font-mono text-xs text-purple-200 border border-white/5" {...props}>
                                                                    {children}
                                                                </code>
                                                            )
                                                        }

                                                        return (
                                                            <div className="my-4 rounded-xl overflow-hidden bg-black/40 border border-white/10 group">
                                                                <div className="flex items-center justify-between px-4 py-2 bg-white/5 border-b border-white/5">
                                                                    <div className="flex items-center gap-2">
                                                                        <Terminal className="w-3.5 h-3.5" />
                                                                        <span className="text-xs font-medium lowercase">{match?.[1] || 'code'}</span>
                                                                    </div>
                                                                    <div className="flex gap-1.5">
                                                                        <div className="w-2.5 h-2.5 rounded-full bg-red-500/20" />
                                                                        <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/20" />
                                                                        <div className="w-2.5 h-2.5 rounded-full bg-green-500/20" />
                                                                    </div>
                                                                </div>
                                                                <div className="p-4 overflow-x-auto selection:bg-purple-500/30">
                                                                    <code className={`block font-mono text-xs leading-relaxed text-neutral-300 whitespace-pre ${className}`} {...props}>
                                                                        {children}
                                                                    </code>
                                                                </div>
                                                            </div>
                                                        )
                                                    },
                                                    table: ({ children }) => (
                                                        <div className="my-6 overflow-hidden rounded-xl border border-white/10">
                                                            <table className="w-full text-left text-sm border-collapse">
                                                                {children}
                                                            </table>
                                                        </div>
                                                    ),
                                                    thead: ({ children }) => (
                                                        <thead className="bg-white/5 text-xs uppercase font-medium">
                                                            {children}
                                                        </thead>
                                                    ),
                                                    th: ({ children }) => (
                                                        <th className="px-4 py-3 border-b border-white/10 font-semibold tracking-wider">
                                                            {children}
                                                        </th>
                                                    ),
                                                    td: ({ children }) => (
                                                        <td className="px-4 py-3 border-b border-white/5 text-neutral-400 group-hover:bg-white/[0.02] transition-colors">
                                                            {children}
                                                        </td>
                                                    ),
                                                    tr: ({ children }) => (
                                                        <tr className="group transition-colors hover:bg-white/[0.02]">
                                                            {children}
                                                        </tr>
                                                    ),
                                                    strong: ({ children }) => (
                                                        <strong className="font-semibold text-white">
                                                            {children}
                                                        </strong>
                                                    ),
                                                    blockquote: ({ children }) => (
                                                        <blockquote className="border-l-2 border-purple-500 pl-4 py-1 my-4 text-neutral-400 italic text-sm">
                                                            {children}
                                                        </blockquote>
                                                    )
                                                }}
                                            >
                                                {msg.content}
                                            </ReactMarkdown>
                                        ) : (
                                            msg.content
                                        )}
                                    </div>
                                </div>
                            ))}
                            {isLoading && (
                                <div className="flex items-start gap-3">
                                    <div className="h-8 w-8 rounded-full bg-linear-to-br from-pink-500 to-purple-600 flex items-center justify-center shrink-0">
                                        <Bot className="h-4 w-4 text-white" />
                                    </div>
                                    <div className="bg-muted/50 border border-white/5 rounded-2xl rounded-tl-sm p-3">
                                        <div className="flex space-x-1">
                                            <div className="w-2 h-2 bg-pink-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                                            <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                                            <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                                        </div>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Input */}
                        <div className="px-4 py-2">
                            <form
                                onSubmit={(e) => sendMessage(e)}
                                className="relative"
                            >
                                <textarea
                                    ref={inputRef}
                                    value={input}
                                    rows={3}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={handleKeyDown}
                                    placeholder="Ask creator AI..."
                                    className="w-full resize-none bg-background border rounded-lg pl-4 pr-12 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/20 transition-all placeholder:text-muted-foreground/50 hide-scrollbar min-h-[46px] max-h-[120px]"
                                    disabled={isLoading}
                                >
                                </textarea>
                                <div className="absolute right-2 bottom-3 flex items-center gap-1">
                                    <button
                                        type="button"
                                        onClick={toggleListening}
                                        className={`h-6 w-6 p-1 flex items-center justify-center rounded-full transition-all border ${isListening ? 'bg-red-500 border-red-500 text-white animate-pulse' : 'bg-white/5 text-zinc-600 hover:text-black hover:bg-white/10'}`}
                                    >
                                        <Mic className={`h-3 w-3 ${isListening ? 'animate-bounce' : ''}`} />
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={isLoading || !input.trim()}
                                        className="h-6 w-6 p-1 flex items-center justify-center rounded-full bg-linear-to-r from-pink-600 to-purple-600 hover:opacity-90 transition-opacity disabled:opacity-50"
                                    >
                                        {isLoading ? <Loader2 className="h-3 w-3 animate-spin text-white" /> : <Send className="h-3 w-3 text-white" />}
                                    </button>
                                </div>
                            </form>
                        </div>

                        {/* Quick actions footer */}
                        <div className="flex justify-between gap-2 px-4 pb-4">
                            {quickActions.map((action) => (
                                <button
                                    key={action.label}
                                    onClick={() => handleQuickAction(action.text)}
                                    className="shrink-0 px-2 py-1.5 text-xs bg-white/5 border rounded-md transition-all text-neutral-400 hover:text-black font-medium flex items-center gap-1"
                                    disabled={isLoading}
                                >
                                    <action.icon className={`w-3.5 h-3.5 transition-colors ${action.color}`} />
                                    {action.label}
                                </button>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <AnimatePresence>
                {!isOpen && (
                    <motion.button
                        initial={{ scale: 0, rotate: 180 }}
                        animate={{ scale: 1, rotate: 0 }}
                        exit={{ scale: 0, rotate: 180 }}
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={toggleChat}
                        className={`group relative h-14 w-14 rounded-full flex items-center justify-center overflow-hidden transition-all duration-300 bg-purple-600 hover:bg-purple-700 shadow-lg shadow-purple-500/30 border border-white/10`}
                    >
                        <motion.div
                            key="chat"
                            initial={{ rotate: 90, opacity: 0 }}
                            animate={{ rotate: 0, opacity: 1 }}
                            exit={{ rotate: -90, opacity: 0 }}
                            transition={{ duration: 0.2 }}
                        >
                            <Sparkles className={`h-6 w-6 text-white`} />
                        </motion.div>
                    </motion.button>
                )}
            </AnimatePresence>
        </div>
    )
}

export default Chatbot