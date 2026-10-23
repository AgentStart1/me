BEGIN { FS = "\"" }
/^\+-o/ { selected = 0 }
{
    for (i = 1; i <= NF - 2; i++) {
        if ($i == "Serial Number") {
            value = $(i + 2)
            sub(/[[:space:]]+$/, "", value)
            selected = value == serial
        }
    }
    if (selected) {
        for (i = 1; i <= NF - 2; i++) {
            if ($i == "BSD Name" && $(i + 2) ~ /^disk[0-9]+$/) names[$(i + 2)] = 1
        }
    }
}
END {
    for (name in names) { count++; result = "/dev/" name }
    if (count != 1) exit 1
    print result
}
