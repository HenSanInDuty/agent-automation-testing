package main

import (
	"log"
	"net/http"
	"time"

	"todo-backend/models"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

var db *gorm.DB

func main() {
	var err error
	db, err = gorm.Open(sqlite.Open("todo.db"), &gorm.Config{})
	if err != nil {
		log.Fatal("failed to connect database")
	}

	// Auto Migrate
	db.AutoMigrate(&models.Task{}, &models.Goal{})

	r := gin.Default()

	// CORS configuration
	r.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"http://localhost:3000"},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))

	api := r.Group("/api")
	{
		api.GET("/tasks", getTasks)
		api.POST("/tasks", createTask)
		api.PUT("/tasks/:id", updateTask)
		api.DELETE("/tasks/:id", deleteTask)

		api.GET("/goals", getGoals)
		api.POST("/goals", createGoal)
		api.DELETE("/goals/:id", deleteGoal)

		api.GET("/stats", getStats)
	}

	r.Run(":8080")
}

// Handlers
func getTasks(c *gin.Context) {
	date := c.Query("date")
	var tasks []models.Task
	query := db.Order("id desc")
	if date != "" {
		query = query.Where("date = ?", date)
	}
	query.Find(&tasks)
	c.JSON(http.StatusOK, tasks)
}

func createTask(c *gin.Context) {
	var input models.Task
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	// Set default date if empty to today? Or require it?
	// For now, let's assume frontend sends it.
	if input.Date == "" {
		input.Date = time.Now().Format("2006-01-02")
	}

	db.Create(&input)
	c.JSON(http.StatusOK, input)
}

func updateTask(c *gin.Context) {
	var task models.Task
	if err := db.First(&task, c.Param("id")).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Task not found"})
		return
	}

	var input map[string]interface{}
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := db.Model(&task).Updates(input).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, task)
}

func deleteTask(c *gin.Context) {
	if err := db.Delete(&models.Task{}, c.Param("id")).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "Task deleted"})
}

func getGoals(c *gin.Context) {
	goalType := c.Query("type")
	date := c.Query("date")
	month := c.Query("month")
	year := c.Query("year")

	var goals []models.Goal
	query := db.Order("id desc")

	if date != "" && month != "" && year != "" {
		// Fetch all goals relevant to the selected date context
		query = query.Where(
			"(type = ? AND date = ?) OR (type = ? AND month = ?) OR (type = ? AND year = ?)",
			"day", date, "month", month, "year", year,
		)
	} else {
		if goalType != "" {
			query = query.Where("type = ?", goalType)
		}
		if date != "" {
			query = query.Where("date = ?", date)
		}
		if month != "" {
			query = query.Where("month = ?", month)
		}
		if year != "" {
			query = query.Where("year = ?", year)
		}
	}

	query.Find(&goals)
	c.JSON(http.StatusOK, goals)
}

func createGoal(c *gin.Context) {
	var input models.Goal
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Automatically setting based on goal type if not provided
	if input.Type == "day" && input.Date == "" {
		input.Date = time.Now().Format("2006-01-02")
	} else if input.Type == "month" && input.Month == "" {
		input.Month = time.Now().Format("2006-01")
	} else if input.Type == "year" && input.Year == "" {
		input.Year = time.Now().Format("2006")
	}

	db.Create(&input)
	c.JSON(http.StatusOK, input)
}

func deleteGoal(c *gin.Context) {
	if err := db.Delete(&models.Goal{}, c.Param("id")).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "Goal deleted"})
}

func getStats(c *gin.Context) {
	// Velocity: All days and last 5 days
	// Return mock data or calculate from DB

	// Calculate for selected date or today
	dateParam := c.Query("date")
	monthParam := c.Query("month")
	targetDate := time.Now()

	if dateParam != "" {
		parsed, err := time.Parse("2006-01-02", dateParam)
		if err == nil {
			targetDate = parsed
		}
	}

	today := targetDate.Format("2006-01-02")
	var totalToday, doneToday int64
	db.Model(&models.Task{}).Where("date = ?", today).Count(&totalToday)
	db.Model(&models.Task{}).Where("date = ? AND is_done = ?", today, true).Count(&doneToday)

	var dailyRate float64
	if totalToday > 0 {
		dailyRate = float64(doneToday) / float64(totalToday) * 100
	}

	// Last 5 days from REAL TODAY
	realToday := time.Now()
	type DayStat struct {
		Date string  `json:"date"`
		Rate float64 `json:"rate"`
	}
	var last5Days []DayStat

	for i := 4; i >= 0; i-- {
		d := realToday.AddDate(0, 0, -i).Format("2006-01-02")
		var t, dn int64
		db.Model(&models.Task{}).Where("date = ?", d).Count(&t)
		db.Model(&models.Task{}).Where("date = ? AND is_done = ?", d, true).Count(&dn)

		rate := 0.0
		if t > 0 {
			rate = float64(dn) / float64(t) * 100
		}
		last5Days = append(last5Days, DayStat{Date: d, Rate: rate})
	}

	// Success days for the month to show streaks in calendar
	successDays := []string{}
	if monthParam != "" {
		// monthParam: YYYY-MM
		// Find all distinct dates in this month from tasks table
		var dates []string
		db.Model(&models.Task{}).Where("date LIKE ?", monthParam+"%").Distinct("date").Pluck("date", &dates)

		for _, d := range dates {
			var total, done int64
			db.Model(&models.Task{}).Where("date = ?", d).Count(&total)
			db.Model(&models.Task{}).Where("date = ? AND is_done = ?", d, true).Count(&done)

			if total > 0 && float64(done)/float64(total) >= 0.8 {
				successDays = append(successDays, d)
			}
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"daily_goal":   dailyRate,
		"last_5_days":  last5Days,
		"success_days": successDays,
	})
}
