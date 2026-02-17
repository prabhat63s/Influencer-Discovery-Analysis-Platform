import { motion } from 'framer-motion'
import { Bot } from 'lucide-react'

const Loading = () => {
  return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/80 backdrop-blur-3xl transition-all duration-500">
          {/* Ambient Background Glows */}
          <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none -z-10">
              <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-purple-500/20 rounded-full blur-[120px] animate-pulse"></div>
              <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-pink-500/20 rounded-full blur-[120px] animate-pulse animation-delay-2000"></div>
          </div>

          <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className="relative flex flex-col items-center"
          >
              {/* Logo Container with Orbiting Rings */}
              <div className="relative mb-12">
                  {/* Outer Ring */}
                  <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                      className="absolute -inset-8 rounded-full border border-purple-500/20 border-t-purple-500/60 border-r-transparent"
                  ></motion.div>
                  {/* Inner Ring */}
                  <motion.div
                      animate={{ rotate: -360 }}
                      transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                      className="absolute -inset-4 rounded-full border border-pink-500/20 border-b-pink-500/60 border-l-transparent"
                  ></motion.div>

                  {/* Main Logo Card */}
                  <div className="relative h-18 w-18 rounded-3xl bg-gradient-to-br from-white/10 to-white/5 dark:from-white/10 dark:to-white/5 backdrop-blur-2xl border border-white/20 flex items-center justify-center overflow-hidden group">
                      <div className="absolute inset-0 bg-gradient-to-br from-pink-500/20 to-purple-600/20 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                      <motion.div
                          animate={{ scale: [1, 1.05, 1] }}
                          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                      >
                          <Bot className="h-10 w-10 text-foreground drop-shadow-[0_0_15px_rgba(168,85,247,0.5)]" />
                      </motion.div>
                  </div>
              </div>

              {/* Text Content */}
              <div className="text-center space-y-4">
                  <motion.h3
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.2, duration: 0.5 }}
                      className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-pink-500 via-purple-500 to-indigo-500"
                  >
                      Creator Connect
                  </motion.h3>

                  <div className="flex items-center justify-center gap-1.5 h-6">
                      <motion.span
                          animate={{ opacity: [0, 1, 0] }}
                          transition={{ duration: 1.5, repeat: Infinity, times: [0, 0.5, 1] }}
                          className="text-pink-500 font-bold"
                      >.</motion.span>
                      <motion.span
                          animate={{ opacity: [0, 1, 0] }}
                          transition={{ duration: 1.5, delay: 0.2, repeat: Infinity, times: [0, 0.5, 1] }}
                          className="text-purple-500 font-bold"
                      >.</motion.span>
                      <motion.span
                          animate={{ opacity: [0, 1, 0] }}
                          transition={{ duration: 1.5, delay: 0.4, repeat: Infinity, times: [0, 0.5, 1] }}
                          className="text-indigo-500 font-bold"
                      >.</motion.span>
                  </div>
              </div>
          </motion.div>
      </div>
  )
}

export default Loading