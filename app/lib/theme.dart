import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// The colour everything else in the app is derived from.
const ovaSeedColor = Color(0xFFC0504D);

/// The app's look: soft rose surfaces, rounded shapes, a rounded display
/// font for headings and a gentle one for everything else.
ThemeData ovaTheme() {
  final colors = ColorScheme.fromSeed(seedColor: ovaSeedColor);
  const background = Color(0xFFFFF6F4);
  const cardRadius = BorderRadius.all(Radius.circular(24));
  const fieldRadius = BorderRadius.all(Radius.circular(16));

  final body = GoogleFonts.nunitoTextTheme(
    ThemeData(colorScheme: colors).textTheme,
  );
  TextStyle? heading(TextStyle? style, [FontWeight weight = FontWeight.w600]) =>
      GoogleFonts.fredoka(
        textStyle: style,
        fontWeight: weight,
        color: colors.onSurface,
      );
  final text = body.copyWith(
    displayLarge: heading(body.displayLarge),
    displayMedium: heading(body.displayMedium),
    displaySmall: heading(body.displaySmall),
    headlineLarge: heading(body.headlineLarge),
    headlineMedium: heading(body.headlineMedium),
    headlineSmall: heading(body.headlineSmall),
    titleLarge: heading(body.titleLarge),
    titleMedium: heading(body.titleMedium, FontWeight.w500),
    titleSmall: heading(body.titleSmall, FontWeight.w500),
    labelLarge: body.labelLarge?.copyWith(fontWeight: FontWeight.w700),
  );

  OutlineInputBorder fieldBorder(Color color, [double width = 1]) =>
      OutlineInputBorder(
        borderRadius: fieldRadius,
        borderSide: BorderSide(color: color, width: width),
      );
  final buttonShape = WidgetStatePropertyAll<OutlinedBorder>(
    const StadiumBorder(),
  );
  final buttonText = WidgetStatePropertyAll(
    GoogleFonts.fredoka(fontSize: 16, fontWeight: FontWeight.w500),
  );
  const buttonSize = WidgetStatePropertyAll(Size(64, 52));

  return ThemeData(
    colorScheme: colors,
    scaffoldBackgroundColor: background,
    textTheme: text,
    appBarTheme: AppBarTheme(
      backgroundColor: background,
      surfaceTintColor: Colors.transparent,
      scrolledUnderElevation: 0,
      titleTextStyle: GoogleFonts.fredoka(
        fontSize: 28,
        fontWeight: FontWeight.w600,
        color: colors.primary,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: Colors.white,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: cardRadius,
        side: BorderSide(color: colors.primary.withValues(alpha: 0.12)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: ButtonStyle(
        shape: buttonShape,
        textStyle: buttonText,
        minimumSize: buttonSize,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: ButtonStyle(
        shape: buttonShape,
        textStyle: buttonText,
        minimumSize: buttonSize,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: ButtonStyle(shape: buttonShape, textStyle: buttonText),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      enabledBorder: fieldBorder(colors.primary.withValues(alpha: 0.25)),
      focusedBorder: fieldBorder(colors.primary, 2),
      errorBorder: fieldBorder(colors.error),
      focusedErrorBorder: fieldBorder(colors.error, 2),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      indicatorColor: colors.primaryContainer,
      height: 72,
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => GoogleFonts.nunito(
          fontSize: 12,
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w800
              : FontWeight.w600,
          color: states.contains(WidgetState.selected)
              ? colors.primary
              : colors.onSurfaceVariant,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? colors.primary
              : colors.onSurfaceVariant,
        ),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: text.headlineSmall,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(28)),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: fieldRadius),
    ),
    dividerTheme: DividerThemeData(
      color: colors.primary.withValues(alpha: 0.12),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      strokeCap: StrokeCap.round,
      color: colors.primary,
    ),
  );
}
