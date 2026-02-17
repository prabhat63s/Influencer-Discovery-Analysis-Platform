"use client"
import React, { useEffect, useState } from 'react'
import Loading from '@/components/Loading'
import { useRouter } from 'next/navigation'

function DashboardLayout({ children }: { children: React.ReactNode }) {
    const router = useRouter()
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        const token = localStorage.getItem('authToken')
        const isLoggedIn = localStorage.getItem('isLoggedIn')

        if (!token && !isLoggedIn) {
            router.push('/')
            return
        }
        // Defer setState to satisfy react-hooks/set-state-in-effect (auth check is sync read)
        const id = setTimeout(() => setIsLoading(false), 0)
        return () => clearTimeout(id)
    }, [router])

    if (isLoading) {
        return <Loading />
    }

    return <div>{children}</div>
}

export default DashboardLayout