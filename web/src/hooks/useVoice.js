import { useCallback, useEffect, useRef, useState } from 'react'
import { transcribe, speak } from '../api'

/** Records from the microphone, transcribes, and speaks replies back.
 *
 *  Transcription goes through ElevenLabs rather than the browser's own speech
 *  API so the result is the same in Safari and Firefox, which either lack
 *  SpeechRecognition or route it through a different engine.
 */
export function useVoice({ enabled = true, voiceId } = {}) {
  const [recording, setRecording] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [level, setLevel] = useState(0)
  const [error, setError] = useState('')

  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)
  const audioRef = useRef(null)
  const rafRef = useRef(null)
  const analyserRef = useRef(null)
  const ctxRef = useRef(null)

  const cleanupStream = useCallback(() => {
    cancelAnimationFrame(rafRef.current)
    setLevel(0)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (ctxRef.current?.state !== 'closed') ctxRef.current?.close().catch(() => {})
    ctxRef.current = null
    analyserRef.current = null
  }, [])

  useEffect(() => () => {
    cleanupStream()
    audioRef.current?.pause()
  }, [cleanupStream])

  // Drives the ring around the mic button so it is obvious we are listening.
  const meter = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser) return
    const data = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteTimeDomainData(data)
    let peak = 0
    for (const v of data) peak = Math.max(peak, Math.abs(v - 128))
    setLevel(Math.min(1, peak / 60))
    rafRef.current = requestAnimationFrame(meter)
  }, [])

  const start = useCallback(async () => {
    setError('')
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser cannot record audio.')
      return false
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
      streamRef.current = stream

      const Ctx = window.AudioContext || window.webkitAudioContext
      const ctx = new Ctx()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 512
      ctx.createMediaStreamSource(stream).connect(analyser)
      ctxRef.current = ctx
      analyserRef.current = analyser
      meter()

      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
        .find((m) => MediaRecorder.isTypeSupported?.(m)) || ''
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data) }
      recorder.start()
      recorderRef.current = recorder
      setRecording(true)
      return true
    } catch (e) {
      setError(
        e.name === 'NotAllowedError'
          ? 'Microphone permission was denied.'
          : `Could not start recording: ${e.message}`
      )
      cleanupStream()
      return false
    }
  }, [meter, cleanupStream])

  /** Stops recording and resolves with the transcript, or '' if nothing usable. */
  const stopAndTranscribe = useCallback(() => new Promise((resolve) => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') { resolve(''); return }

    recorder.onstop = async () => {
      cleanupStream()
      setRecording(false)
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      // Anything this short is a mis-tap, not speech.
      if (blob.size < 2000) { resolve(''); return }
      setThinking(true)
      try {
        const { text } = await transcribe(blob)
        resolve((text || '').trim())
      } catch (e) {
        setError(`Could not transcribe: ${e.message}`)
        resolve('')
      } finally {
        setThinking(false)
      }
    }
    recorder.stop()
  }), [cleanupStream])

  const say = useCallback(async (text) => {
    if (!enabled || !text) return
    try {
      audioRef.current?.pause()
      const url = await speak(text, voiceId)
      if (!url) return
      const audio = new Audio(url)
      audioRef.current = audio
      setSpeaking(true)
      audio.onended = audio.onerror = () => { setSpeaking(false); URL.revokeObjectURL(url) }
      await audio.play()
    } catch {
      setSpeaking(false) // Autoplay policies can refuse; silence is acceptable.
    }
  }, [enabled, voiceId])

  const stopSpeaking = useCallback(() => {
    audioRef.current?.pause()
    setSpeaking(false)
  }, [])

  return { recording, thinking, speaking, level, error,
           start, stopAndTranscribe, say, stopSpeaking, setError }
}
