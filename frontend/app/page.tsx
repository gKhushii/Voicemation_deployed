"use client"

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Mic,
  Square,
  Play,
  Loader2,
  Sparkles,
  Clock,
  History,
  Sun,
  Moon,
  ChevronRight,
  Download,
  Video,
  ArrowRight,
  AlertCircle,
} from "lucide-react"

interface Subtitle {
  start: number
  end: number
  text: string
}

interface HistoryItem {
  id: string
  timestamp: Date
  videoUrl: string
  subtitles: Subtitle[]
  durationMode: "ai" | "manual"
  manualDuration: string
  title: string
}

export default function VoicemationApp() {
  const [isRecording, setIsRecording] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [status, setStatus] = useState("")
  const [videoUrl, setVideoUrl] = useState("")
  const [subtitles, setSubtitles] = useState<Subtitle[]>([])
  const [durationMode, setDurationMode] = useState<"ai" | "manual">("ai")
  const [manualDuration, setManualDuration] = useState("30")
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [theme, setTheme] = useState<"light" | "dark">("dark")
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [duration, setDuration] = useState<number>(30) // New state for duration
  const [recordingStartTime, setRecordingStartTime] = useState<number>(0) // New state for recording start time

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const savedHistory = localStorage.getItem("voicemation_history")
    if (savedHistory) {
      const parsed = JSON.parse(savedHistory)
      setHistory(parsed.map((item: any) => ({ ...item, timestamp: new Date(item.timestamp) })))
    }

    const savedTheme = localStorage.getItem("voicemation_theme") as "light" | "dark" | null
    if (savedTheme) {
      setTheme(savedTheme)
    }
  }, [])

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
    localStorage.setItem("voicemation_theme", theme)
  }, [theme])

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.playbackRate = playbackSpeed
    }
  }, [playbackSpeed, videoUrl])

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []
      setRecordingStartTime(Date.now()) // Track when recording starts

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data)
      }

      mediaRecorder.onstop = async () => {
        const recordingDuration = (Date.now() - recordingStartTime) / 1000 // seconds
        console.log("[v0] Recording duration:", recordingDuration, "seconds")

        if (recordingDuration < 1) {
          setStatus("Error: Recording too short. Please record at least 1 second of audio.")
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" })
        console.log("[v0] Audio blob size:", blob.size, "bytes")
        if (blob.size < 1000) {
          setStatus("Error: Audio recording failed. Please try again and speak clearly.")
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        setAudioBlob(blob)
        await handleGenerateVideo(blob)
        stream.getTracks().forEach((track) => track.stop())
      }

      mediaRecorder.start()
      setIsRecording(true)
      setStatus("Recording...")
    } catch (error) {
      setStatus("Error: Could not access microphone. Check permissions.")
      console.error("Microphone access error:", error)
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }

  const handleGenerateVideo = async (blob?: Blob) => {
    const audioToUse = blob || audioBlob

    if (!audioToUse) {
      setStatus("No audio recorded")
      return
    }

    setIsGenerating(true)
    setStatus("Generating animation...")

    try {
      console.log("[v0] Starting generation with audio blob")
      console.log("[v0] Audio blob size:", audioToUse.size, "bytes")
      console.log("[v0] Audio blob type:", audioToUse.type)
      console.log("[v0] Duration mode:", durationMode)
      console.log("[v0] Duration value:", duration)

      const formData = new FormData()
      formData.append("audio", audioToUse, "audio.webm")
      formData.append("duration_limit", durationMode === "ai" ? "0" : duration.toString())

      const FLASK_URL = "http://127.0.0.1:5001"
      const endpoint = `${FLASK_URL}/generate_audio`

      console.log("[v0] Sending request to Flask backend:", endpoint)

      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
        mode: "cors",
      })

      console.log("[v0] Response status:", response.status)
      console.log("[v0] Response headers:", Object.fromEntries(response.headers.entries()))

      const contentType = response.headers.get("content-type")
      if (!contentType || !contentType.includes("application/json")) {
        const text = await response.text()
        console.error("[v0] Non-JSON response:", text.substring(0, 200))
        throw new Error(
          "Flask backend returned HTML instead of JSON. Check that the endpoint exists and CORS is enabled.",
        )
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        console.error("[v0] Flask error response:", errorData)
        throw new Error(`HTTP error! status: ${response.status}${errorData?.error ? ` - ${errorData.error}` : ""}`)
      }

      const result = await response.json()
      console.log("[v0] Response from Flask:", result)

      if (result.video_url) {
        const fullVideoUrl = result.video_url.startsWith("http") ? result.video_url : `${FLASK_URL}${result.video_url}`
        const newVideoUrl = fullVideoUrl + "?t=" + new Date().getTime()
        const newSubtitles = result.subtitles_json || []

        const fullText = newSubtitles.map((s) => s.text).join(" ")
        console.log("[v0] Extracted subtitle text:", fullText)

        const titleText =
          fullText.length > 0 ? fullText.slice(0, 50) + (fullText.length > 50 ? "..." : "") : "Untitled Recording"

        console.log("[v0] Title for history:", titleText)

        setVideoUrl(newVideoUrl)
        setSubtitles(newSubtitles)
        setStatus("Animation generated successfully!")

        const newHistoryItem: HistoryItem = {
          id: Date.now().toString(),
          timestamp: new Date(),
          videoUrl: newVideoUrl,
          subtitles: newSubtitles,
          durationMode,
          manualDuration,
          title: titleText,
        }

        console.log("[v0] Adding to history:", newHistoryItem)

        const updatedHistory = [newHistoryItem, ...history]
        setHistory(updatedHistory)
        localStorage.setItem("voicemation_history", JSON.stringify(updatedHistory))

        setTimeout(() => {
          if (videoRef.current) {
            videoRef.current.playbackRate = playbackSpeed
            videoRef.current.play().catch(() => {})
          }
        }, 100)
      } else {
        setStatus("Error: " + (result.error || "Unknown error occurred"))
      }
    } catch (error) {
      const errorMessage = (error as Error).message
      console.error("[v0] Generation error:", error)

      if (errorMessage.includes("Failed to fetch")) {
        setStatus(
          "Cannot connect to Flask backend. Make sure it's running on http://127.0.0.1:5001 and CORS is enabled.",
        )
      } else {
        setStatus("Error: " + errorMessage)
      }
    } finally {
      setIsGenerating(false)
    }
  }

  const loadHistoryItem = (item: HistoryItem) => {
    setVideoUrl(item.videoUrl)
    setSubtitles(item.subtitles)
    setDurationMode(item.durationMode)
    setManualDuration(item.manualDuration)
    setIsHistoryOpen(false)
    setTimeout(() => {
      if (videoRef.current) {
        videoRef.current.playbackRate = playbackSpeed
      }
    }, 100)
  }

  const renderSubtitles = () => {
    if (!subtitles || subtitles.length === 0) {
      return <p className="text-muted-foreground">Subtitles will appear here when the video is generated.</p>
    }

    const SCENE_BREAK = 10
    const paragraphs: string[] = []
    let currentParagraph: string[] = []

    subtitles.forEach((sub, idx) => {
      currentParagraph.push(sub.text)
      if ((idx + 1) % SCENE_BREAK === 0) {
        paragraphs.push(currentParagraph.join(" "))
        currentParagraph = []
      }
    })

    if (currentParagraph.length) {
      paragraphs.push(currentParagraph.join(" "))
    }

    return paragraphs.map((paragraph, idx) => (
      <p key={idx} className="mb-4 leading-relaxed">
        {paragraph}
      </p>
    ))
  }

  const getDurationHint = () => {
    if (durationMode === "ai") {
      return "AI will determine the optimal duration based on the content."
    }
    return `Video length is manually capped at ${manualDuration === "30" ? "30 seconds" : manualDuration === "60" ? "1 minute" : manualDuration === "120" ? "2 minutes" : manualDuration === "180" ? "3 minutes" : "5 minutes"}.`
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur-sm border-b border-border/50">
        <div className="container max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1">
              <h1 className="text-2xl lg:text-3xl font-bold tracking-tight text-foreground">Voicemation</h1>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="icon"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="shrink-0"
              >
                {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setIsHistoryOpen(!isHistoryOpen)}
                className="shrink-0"
              >
                <History className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="container max-w-5xl mx-auto px-4 py-8 space-y-8">
        <div className="text-center space-y-6 py-12">
          <h2 className="text-4xl lg:text-5xl font-bold bg-gradient-to-r from-blue-500 via-primary to-blue-600 bg-clip-text text-transparent">
            Welcome to Voicemation
          </h2>
          <p className="text-lg text-muted-foreground">Your Voice, Our Animations</p>

          <div className="flex items-center justify-center gap-4 py-6">
            <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center">
              <Mic className="w-8 h-8 text-primary" />
            </div>
            <ArrowRight className="w-8 h-8 text-muted-foreground" />
            <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center">
              <Video className="w-8 h-8 text-primary" />
            </div>
          </div>
        </div>

        <Card className="p-8 space-y-6 max-w-2xl mx-auto">
          <div className="text-center space-y-4">
            <h3 className="text-xl font-semibold">Record Your Voice</h3>

            <div className="flex items-center justify-center gap-3">
              <Button
                variant={durationMode === "ai" ? "default" : "outline"}
                size="sm"
                onClick={() => setDurationMode("ai")}
                className="gap-2"
              >
                <Sparkles className="w-4 h-4" />
                AI Duration
              </Button>

              <Button
                variant={durationMode === "manual" ? "default" : "outline"}
                size="sm"
                onClick={() => setDurationMode("manual")}
                className="gap-2"
              >
                <Clock className="w-4 h-4" />
                Manual
              </Button>

              {durationMode === "manual" && (
                <select
                  value={manualDuration}
                  onChange={(e) => {
                    setManualDuration(e.target.value)
                    setDuration(Number.parseInt(e.target.value)) // Update duration state
                  }}
                  className="px-3 py-1.5 rounded-lg border border-border bg-card text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="30">30s</option>
                  <option value="60">1m</option>
                  <option value="120">2m</option>
                  <option value="180">3m</option>
                  <option value="300">5m</option>
                </select>
              )}
            </div>

            <p className="text-sm text-muted-foreground">
              {durationMode === "ai"
                ? "AI will decide your animation length based on the content."
                : "Select the video length. The video would be approximately the length specified."}
            </p>
          </div>

          <div className="relative flex items-center justify-center py-8">
            {isRecording && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-32 h-32 rounded-full bg-primary/20 animate-ping" />
                <div
                  className="absolute w-40 h-40 rounded-full bg-primary/10 animate-ping"
                  style={{ animationDelay: "0.5s" }}
                />
                <div
                  className="absolute w-48 h-48 rounded-full bg-primary/5 animate-ping"
                  style={{ animationDelay: "1s" }}
                />
              </div>
            )}

            <div className="relative z-10">
              {/* Outer border ring with gradient */}
              <div
                className={`absolute -inset-1 rounded-full bg-gradient-to-br from-primary via-blue-500 to-primary opacity-75 blur-md ${isRecording ? "animate-pulse" : ""}`}
              />

              {/* Middle border ring */}
              <div className="absolute -inset-0.5 rounded-full bg-gradient-to-br from-primary to-blue-600 opacity-100" />

              {/* Button container with border */}
              <div className="relative">
                <Button
                  size="lg"
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={isGenerating}
                  className={`relative w-24 h-24 rounded-full shadow-2xl border-4 border-background transition-all duration-300 ${
                    isRecording
                      ? "bg-gradient-to-br from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 scale-95"
                      : "bg-gradient-to-br from-primary to-blue-600 hover:from-blue-600 hover:to-primary hover:scale-110"
                  } ${isGenerating ? "cursor-not-allowed opacity-70" : ""}`}
                >
                  {isGenerating ? (
                    <Loader2 className="w-8 h-8 animate-spin" />
                  ) : isRecording ? (
                    <Square className="w-8 h-8 fill-current" />
                  ) : (
                    <Mic className="w-8 h-8" />
                  )}
                </Button>
              </div>
            </div>
          </div>

          <p className="text-center text-sm text-muted-foreground">
            {isRecording ? "Recording in progress..." : "Click to start recording"}
          </p>

          {status && (
            <div
              className={`flex items-start gap-3 p-4 rounded-lg ${
                status.includes("Error") || status.includes("Cannot connect")
                  ? "bg-destructive/10 border border-destructive/20"
                  : "bg-muted/50"
              }`}
            >
              {status.includes("Error") || status.includes("Cannot connect") ? (
                <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
              ) : (
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0 mt-2" />
              )}
              <div className="flex-1 space-y-1">
                <p className="text-sm font-medium text-foreground">{status}</p>
                {status.includes("Cannot connect") && (
                  <div className="text-xs text-muted-foreground space-y-1 mt-2">
                    <p className="font-semibold">To fix this:</p>
                    <ol className="list-decimal list-inside space-y-1 ml-2">
                      <li>
                        Make sure Flask is running: <code className="bg-muted px-1 py-0.5 rounded">python app.py</code>
                      </li>
                      <li>
                        Add CORS to Flask:{" "}
                        <code className="bg-muted px-1 py-0.5 rounded">from flask_cors import CORS; CORS(app)</code>
                      </li>
                      <li>Download this app and run locally to connect to your Flask server</li>
                    </ol>
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>

        {videoUrl && (
          <div className="space-y-6">
            <Card className="overflow-hidden">
              <div className="relative bg-black">
                <video ref={videoRef} src={videoUrl} controls className="w-full aspect-video" />
              </div>
              <div className="p-5 border-t border-border space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-semibold flex items-center gap-2">
                    <Play className="w-4 h-4 text-primary" />
                    Playback Speed
                  </label>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-2 text-xs"
                    onClick={() => {
                      const a = document.createElement("a")
                      a.href = videoUrl
                      a.download = "voicemation-video.mp4"
                      a.click()
                    }}
                  >
                    <Download className="w-4 h-4" />
                    Download
                  </Button>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {[0.5, 0.75, 1.0, 1.25, 1.5, 2.0].map((speed) => (
                    <Button
                      key={speed}
                      variant={playbackSpeed === speed ? "default" : "outline"}
                      size="sm"
                      onClick={() => setPlaybackSpeed(speed)}
                      className="min-w-[60px]"
                    >
                      {speed}x
                    </Button>
                  ))}
                </div>
              </div>
            </Card>

            <Card className="p-6">
              <div className="flex items-center gap-2 mb-4 pb-3 border-b border-border">
                <div className="w-1 h-6 bg-primary rounded-full" />
                <h2 className="text-xl font-semibold">Subtitles</h2>
              </div>
              <div className="max-h-80 overflow-y-auto text-sm space-y-2 leading-relaxed pr-2 custom-scrollbar">
                {renderSubtitles()}
              </div>
            </Card>
          </div>
        )}
      </div>

      <div
        className={`fixed top-0 right-0 h-full w-96 bg-card/95 backdrop-blur-md border-l border-border shadow-2xl transform transition-all duration-300 overflow-hidden z-50 ${
          isHistoryOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="h-full flex flex-col">
          <div className="p-6 border-b border-border bg-gradient-to-b from-card to-card/50">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <History className="w-5 h-5 text-primary" />
                History
              </h2>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsHistoryOpen(false)}
                className="hover:scale-110 transition-transform"
              >
                <ChevronRight className="w-5 h-5" />
              </Button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-3 custom-scrollbar">
            {history.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center space-y-3 p-8">
                <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
                  <History className="w-8 h-8 text-muted-foreground" />
                </div>
                <p className="text-muted-foreground text-sm">No history yet. Generate your first video!</p>
              </div>
            ) : (
              history.map((item, idx) => (
                <Card
                  key={item.id}
                  className="p-4 cursor-pointer hover:bg-accent/50 hover:shadow-lg transition-all duration-200 hover:scale-[1.02] border-border/50 animate-in fade-in slide-in-from-right"
                  style={{ animationDelay: `${idx * 50}ms` }}
                  onClick={() => loadHistoryItem(item)}
                >
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold text-foreground line-clamp-2 leading-snug">{item.title}</h3>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {item.durationMode === "ai" ? (
                          <>
                            <Sparkles className="w-3 h-3 text-primary" />
                            <p className="text-xs text-muted-foreground">AI Duration</p>
                          </>
                        ) : (
                          <>
                            <Clock className="w-3 h-3 text-primary" />
                            <p className="text-xs text-muted-foreground">Manual - {item.manualDuration}s</p>
                          </>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">{item.timestamp.toLocaleTimeString()}</p>
                    </div>
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>
      </div>

      {isHistoryOpen && (
        <div
          className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40 animate-in fade-in duration-300"
          onClick={() => setIsHistoryOpen(false)}
        />
      )}
    </main>
  )
}
