// Edge Function to generate beta diversity visualization data
// @ts-ignore
import * as postgres from 'https://deno.land/x/postgres@v0.17.0/mod.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// Calculate Bray-Curtis dissimilarity between two samples
function brayCurtisDistance(sample1: number[], sample2: number[]): number {
  let sumMin = 0
  let sum1 = 0
  let sum2 = 0

  for (let i = 0; i < sample1.length; i++) {
    sumMin += Math.min(sample1[i], sample2[i])
    sum1 += sample1[i]
    sum2 += sample2[i]
  }

  // Handle edge case where both samples are all zeros
  if (sum1 === 0 && sum2 === 0) {
    return 0
  }

  // Bray-Curtis formula: 1 - (2 * sum_min) / (sum1 + sum2)
  return 1 - (2 * sumMin) / (sum1 + sum2)
}

// Calculate full distance matrix for all sample pairs
function calculateBetaDiversityMatrix(data: number[][]): number[][] {
  const numSamples = data.length
  const distanceMatrix: number[][] = []

  // Initialize matrix with zeros
  for (let i = 0; i < numSamples; i++) {
    distanceMatrix[i] = new Array(numSamples).fill(0)
  }

  // Calculate pairwise distances
  for (let i = 0; i < numSamples; i++) {
    for (let j = i + 1; j < numSamples; j++) {
      const distance = brayCurtisDistance(data[i], data[j])
      distanceMatrix[i][j] = distance
      distanceMatrix[j][i] = distance // Matrix is symmetric
    }
  }

  return distanceMatrix
}

// Parse string value to number, default to 0 for non-numeric
function parseNumeric(value: string | number): number {
  if (typeof value === 'number') return value
  const parsed = parseFloat(value)
  return isNaN(parsed) ? 0 : parsed
}

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  const startTime = Date.now()

  try {
    // Parse request body
    const { table_name, row_limit = 50, column_limit = 10 } = await req.json().catch(() => ({}))

    if (!table_name) {
      return new Response(
        JSON.stringify({ success: false, error: 'table_name is required' }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
      )
    }

    // Validate limits
    const maxRowLimit = 1000
    const maxColLimit = 500
    const validRowLimit = Math.min(Math.max(1, row_limit), maxRowLimit)
    const validColLimit = Math.min(Math.max(2, column_limit), maxColLimit)

    // Connect to PostgreSQL
    const databaseUrl = Deno.env.get('SUPABASE_DB_URL')!
    const pool = new postgres.Pool(databaseUrl, 3, true)
    const connection = await pool.connect()

    try {
      // Verify table exists
      const tableCheck = await connection.queryObject(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables
          WHERE table_schema = '_fd' AND table_name = $1
        )`,
        [table_name]
      )

      if (!tableCheck.rows[0]?.exists) {
        return new Response(
          JSON.stringify({
            success: false,
            error: `Table '${table_name}' not found in _fd schema`
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
        )
      }

      // Get column names (excluding rowid and first column which is patient ID)
      const columnsResult = await connection.queryObject(
        `SELECT column_name
         FROM information_schema.columns
         WHERE table_schema = '_fd' AND table_name = $1
         AND column_name NOT IN ('rowid')
         ORDER BY ordinal_position
         LIMIT $2`,
        [table_name, validColLimit + 1] // +1 to get patient ID column
      )

      const allColumns = columnsResult.rows.map(row => row.column_name as string)

      // First column is patient/sample ID, rest are data columns
      const patientCol = allColumns[0]
      const dataColumns = allColumns.slice(1, validColLimit + 1) // Limit to validColLimit samples

      if (dataColumns.length < 2) {
        return new Response(
          JSON.stringify({
            success: false,
            error: 'Table must have at least 2 data columns for beta diversity calculation'
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
        )
      }

      // Build column list for SQL query
      const columnsList = dataColumns.map(col => `"${col}"`).join(', ')

      // Query data
      const dataResult = await connection.queryObject(
        `SELECT ${columnsList}
         FROM _fd."${table_name}"
         LIMIT $1`,
        [validRowLimit]
      )

      if (dataResult.rows.length === 0) {
        return new Response(
          JSON.stringify({
            success: false,
            error: 'No data found in table'
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
        )
      }

      // Transform data: rows are samples, columns are OTUs/features
      // We need to transpose: each sample becomes a vector of abundances
      const sampleData: number[][] = []

      for (let colIdx = 0; colIdx < dataColumns.length; colIdx++) {
        const sampleName = dataColumns[colIdx]
        const abundances: number[] = []

        // Collect all abundances for this sample across all OTUs
        for (const row of dataResult.rows) {
          const value = row[sampleName]
          abundances.push(parseNumeric(value as string))
        }

        sampleData.push(abundances)
      }

      // Calculate beta diversity matrix
      const distanceMatrix = calculateBetaDiversityMatrix(sampleData)

      // Get total column count for metadata
      const totalColsResult = await connection.queryObject(
        `SELECT COUNT(*) as count
         FROM information_schema.columns
         WHERE table_schema = '_fd' AND table_name = $1
         AND column_name NOT IN ('rowid')`,
        [table_name]
      )

      const totalColumns = Number(totalColsResult.rows[0]?.count || 0) - 1 // -1 for patient ID column

      const processingTime = Date.now() - startTime

      // Prepare response
      const responseData = {
        success: true,
        data: {
          distance_matrix: distanceMatrix,
          sample_names: dataColumns,
          row_count: dataResult.rows.length,
          column_count: dataColumns.length,
          total_columns_available: totalColumns,
          metric: 'bray_curtis'
        },
        metadata: {
          table_name,
          processing_time_ms: processingTime,
          row_limit: validRowLimit,
          column_limit: validColLimit
        }
      }

      return new Response(
        JSON.stringify(responseData),
        {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          status: 200,
        },
      )

    } finally {
      connection.release()
    }

  } catch (error) {
    console.error('Error in get-dataset-visualization:', error)
    return new Response(
      JSON.stringify({
        success: false,
        error: error.message || 'Internal server error'
      }),
      {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 500,
      },
    )
  }
})
