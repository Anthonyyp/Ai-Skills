; Script-Fu self-test. Run with:
;     python scripts/gimp_cli.py scm tests/selftest.scm
;
; Confirms the GIMP 3 Script-Fu shapes the reference doc claims: return values
; still arrive wrapped in lists, and the export procedures use the 3.x names.

(let* ((width 320)
       (height 240)
       ; Every PDB call returns a LIST. car unwraps the first return value.
       ; This is unchanged from 2.10 and is the #1 source of Script-Fu bugs.
       (image (car (gimp-image-new width height RGB)))
       (layer (car (gimp-layer-new image "bg" width height RGBA-IMAGE 100 LAYER-MODE-NORMAL)))
       ; gimp-temp-file keeps this test portable - TinyScheme has no way to
       ; read an environment variable or build a platform temp path.
       (out (car (gimp-temp-file "png"))))

  (gimp-image-insert-layer image layer 0 0)

  ; context colours take a colour object; a hex string works
  (gimp-context-set-background "#204060")
  (gimp-drawable-fill layer FILL-BACKGROUND)

  (gimp-context-set-foreground "#e8a33d")
  (gimp-image-select-ellipse image CHANNEL-OP-REPLACE 60 40 200 160)
  (gimp-drawable-fill layer FILL-FOREGROUND)
  (gimp-selection-none image)

  (gimp-message (string-append "image is "
                               (number->string (car (gimp-image-get-width image)))
                               "x"
                               (number->string (car (gimp-image-get-height image)))))

  ; GIMP 3: file-png-save is GONE, it is file-png-export, and the argument
  ; list changed - (run-mode image file options...) with a single image arg
  ; rather than the old (run-mode image drawable filename raw-filename ...).
  (file-png-export RUN-NONINTERACTIVE image out 0)

  (gimp-message (string-append "wrote " out))
  (gimp-message "script-fu selftest OK")
  (gimp-image-delete image))
